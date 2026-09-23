"""
LiveKit Agents 1.7-compatible concert voice agent.

This replaces the old LiveKit 0.x VoicePipelineAgent/FunctionContext architecture
with Agent + AgentSession + function_tool.

Preserved from the original implementation:
- Cartesia Ink-Whisper STT
- Dynamic English/Hindi Cartesia TTS
- Groq (gpt-oss-20b -> gpt-oss-120b) -> Gemini -> Gemini secondary LLM fallback
- SIP and authenticated website sessions
- Existing voice_db booking functions
- Session transcript + summary persistence
"""

import asyncio
import logging
import os
from datetime import datetime
from typing import Any

from app.logger import session_id_var

from livekit.agents import (
    Agent,
    AgentSession,
    APIConnectOptions,
    DEFAULT_API_CONNECT_OPTIONS,
    JobContext,
    WorkerOptions,
    cli,
    llm,
    utils,
)
from livekit import rtc
from livekit.plugins import cartesia, openai, silero

from app.voice_agent import voice_config as config
from app.voice_agent import voice_db
from app.voice_agent.tools import ConcertBookingTools, ConcertBookingToolsWeb
from app.agents import memory

logger = logging.getLogger("receptionist_agent")


def _detect_hindi(text: str) -> bool:
    """Return True when the text contains a meaningful amount of Devanagari."""
    if not text:
        return False
    devanagari_count = sum(
        1 for ch in text if "\u0900" <= ch <= "\u097F"
    )
    return devanagari_count > len(text) * 0.20


# ---------------------------------------------------------------------------
# Greeting caching — the opening line is IDENTICAL for every single session,
# so synthesizing it fresh via Cartesia TTS on every connect (as the plain
# `await session.say(greeting)` call used to do) burns TTS credits for zero
# benefit. Render it once per worker process, cache the audio frames, and
# replay the cached audio on every subsequent session via say(..., audio=...)
# — which, per livekit-agents 1.7's own _tts_task_impl, skips calling the
# TTS model entirely when `audio` is provided. Mirrors tata_voice_server.py's
# precompute_greeting() for the phone-call path.
# ---------------------------------------------------------------------------
_greeting_audio_cache: dict[str, list[rtc.AudioFrame]] = {}


async def _get_cached_greeting_audio(tts_provider, text: str) -> list[rtc.AudioFrame]:
    if text in _greeting_audio_cache:
        return _greeting_audio_cache[text]

    frames: list[rtc.AudioFrame] = []
    async for synthesized in tts_provider.synthesize(text):
        frames.append(synthesized.frame)

    _greeting_audio_cache[text] = frames
    logger.info(f"Pre-rendered and cached greeting audio ({len(frames)} frames) for reuse.")
    return frames


async def _replay_cached_audio(frames: list[rtc.AudioFrame]):
    """Async generator wrapping pre-rendered frames for session.say(audio=...)."""
    for frame in frames:
        yield frame




import time
from livekit.agents._exceptions import APIConnectionError

class CooldownAwareLLM(llm.LLM):
    """Wraps an LLM instance to track 429s and avoid hammering it while rate-limited."""
    def __init__(self, inner: llm.LLM, cooldown_seconds: float = 60.0):
        super().__init__()
        self._inner = inner
        self._cooldown_seconds = cooldown_seconds
        self._cooldown_until: float = 0.0

    @property
    def label(self) -> str: return self._inner.label

    @property
    def model(self) -> str: return self._inner.model

    @property
    def provider(self) -> str: return self._inner.provider

    def _update_metrics(self, *args, **kwargs):
        self.emit("metrics_collected", *args, **kwargs)

    def _start(self):
        self._inner.on("metrics_collected", self._update_metrics)
        
    def _stop(self):
        self._inner.off("metrics_collected", self._update_metrics)

    def chat(self, *, chat_ctx, tools=None, **kwargs):
        if time.time() < self._cooldown_until:
            logger.warning(f"{self.label} is currently on cooldown due to recent 429.")
            raise APIConnectionError("LLM on cooldown due to rate limits")

        # Create a clean context for strict providers to avoid 'extra_content' HTTP 400s
        from livekit.agents.llm import ChatContext, ChatMessage, FunctionCall
        clean_ctx = ChatContext()
        
        is_gemini = "gemini" in getattr(self._inner, "label", "").lower() or "gemini" in str(getattr(self._inner, "model", "")).lower()
        
        for item in getattr(chat_ctx, "items", getattr(chat_ctx, "messages", [])):
            if is_gemini:
                # Do not strip extra for Gemini as it requires thought_signature
                clean_ctx._items.append(item)
                continue
                
            if isinstance(item, ChatMessage) and getattr(item, "extra", None):
                # Pydantic v1/v2 compatibility copy
                clean_msg = item.copy() if hasattr(item, "copy") else item.model_copy()
                clean_msg.extra = {}
                clean_ctx._items.append(clean_msg)
            elif isinstance(item, FunctionCall) and getattr(item, "extra", None):
                clean_fc = item.copy() if hasattr(item, "copy") else item.model_copy()
                clean_fc.extra = {}
                clean_ctx._items.append(clean_fc)
            else:
                clean_ctx._items.append(item)

        stream = self._inner.chat(chat_ctx=clean_ctx, tools=tools, **kwargs)
        original_aiter = stream.__aiter__
        
        async def hooked_aiter():
            try:
                async for chunk in original_aiter():
                    yield chunk
            except Exception as e:
                retry_after = None
                headers = {}
                if hasattr(e, "response") and hasattr(e.response, "headers"):
                    headers = e.response.headers
                elif hasattr(e, "__cause__") and e.__cause__ and hasattr(e.__cause__, "response") and hasattr(e.__cause__.response, "headers"):
                    headers = e.__cause__.response.headers

                if "429" in str(e) or "Too Many Requests" in str(e) or "quota" in str(e).lower():
                    if headers:
                        retry_after_str = headers.get("retry-after")
                        reset_tokens_str = headers.get("x-ratelimit-reset-tokens")
                        
                        if retry_after_str:
                            try:
                                retry_after = float(retry_after_str)
                            except ValueError:
                                pass
                        elif reset_tokens_str:
                            try:
                                retry_after = float(reset_tokens_str)
                            except ValueError:
                                pass

                    cooldown = retry_after if retry_after is not None else self._cooldown_seconds
                    logger.warning(
                        f"[GROQ RATE LIMIT] status=429 "
                        f"remaining_tokens={headers.get('x-ratelimit-remaining-tokens', 'N/A')} "
                        f"reset_tokens={headers.get('x-ratelimit-reset-tokens', 'N/A')} "
                        f"retry_after={headers.get('retry-after', 'N/A')} "
                        f"cooldown={cooldown}"
                    )
                    self._cooldown_until = time.time() + cooldown
                raise e

        stream.__aiter__ = hooked_aiter
        return stream


class SanitizedGeminiLLM(llm.LLM):
    """
    Wraps Gemini to intercept the chat context and sanitize any foreign tool calls 
    (which lack a thought_signature) into neutral conversational text, preventing 
    strict validation errors on fallback.
    """
    def __init__(self, inner: llm.LLM):
        super().__init__()
        self._inner = inner

    @property
    def label(self) -> str:
        return getattr(self._inner, "label", "SanitizedGemini")

    def _sanitize_ctx(self, chat_ctx: llm.ChatContext) -> llm.ChatContext:
        from livekit.agents.llm import ChatContext, ChatMessage, FunctionCall, FunctionCallOutput
        new_ctx = ChatContext()
        foreign_tool_ids = set()
        sanitized_call_ids = set()
        
        def sanitize_foreign_fc(tc: FunctionCall):
            is_foreign = True
            if getattr(tc, "extra", None) and "google" in tc.extra and "thought_signature" in tc.extra["google"]:
                is_foreign = False
            
            if is_foreign:
                foreign_tool_ids.add(tc.call_id)
                if tc.call_id not in sanitized_call_ids:
                    sanitized_call_ids.add(tc.call_id)
                    new_msg = ChatMessage(
                        role="assistant", 
                        content=[f"[System note: I decided to execute tool: {tc.name}]"]
                    )
                    new_ctx._items.append(new_msg)
                    logger.info(f"Sanitized foreign tool call {tc.name} into neutral text for Gemini.")
                return True
            return False

        for item in getattr(chat_ctx, "items", []):
            if isinstance(item, ChatMessage):
                if getattr(item, "tool_calls", None):
                    clean_tool_calls = []
                    for tc in item.tool_calls:
                        if not sanitize_foreign_fc(tc):
                            clean_tool_calls.append(tc)
                    
                    clean_msg = item.model_copy()
                    clean_msg.tool_calls = clean_tool_calls if clean_tool_calls else None
                    
                    # Check if message is empty after stripping
                    has_content = False
                    if clean_msg.content:
                        if isinstance(clean_msg.content, str):
                            has_content = bool(clean_msg.content.strip())
                        elif isinstance(clean_msg.content, list):
                            has_content = len(clean_msg.content) > 0
                            
                    if not clean_msg.tool_calls and not has_content:
                        continue
                    
                    new_ctx._items.append(clean_msg)
                else:
                    new_ctx._items.append(item)
            elif isinstance(item, FunctionCall):
                if not sanitize_foreign_fc(item):
                    new_ctx._items.append(item)
            elif isinstance(item, FunctionCallOutput):
                if item.call_id in foreign_tool_ids:
                    new_msg = ChatMessage(
                        role="user",
                        content=[f"[System note: Tool '{item.name}' returned: {item.output}]"]
                    )
                    new_ctx._items.append(new_msg)
                    logger.info("Sanitized foreign tool response into neutral text for Gemini.")
                else:
                    new_ctx._items.append(item)
            else:
                new_ctx._items.append(item)
                
        return new_ctx

    def chat(self, *, chat_ctx, tools=None, **kwargs):
        sanitized_ctx = self._sanitize_ctx(chat_ctx)
        return self._inner.chat(chat_ctx=sanitized_ctx, tools=tools, **kwargs)


class NoRetryFallbackAdapter(llm.LLM):
    """
    Wraps the FallbackAdapter to enforce max_retry=0 globally for its outer loop,
    preventing already-exhausted fallback chains from repeating multiple times.
    """
    def __init__(self, adapter: llm.LLM):
        super().__init__()
        self.adapter = adapter
        
    @property
    def label(self) -> str:
        return getattr(self.adapter, "label", "NoRetryFallbackAdapter")
        
    def chat(self, *, chat_ctx, tools=None, conn_options=None, **kwargs):
        from livekit.agents import APIConnectOptions
        # Ignore outer retries by forcing max_retry to 0
        no_retry_opts = APIConnectOptions(
            max_retry=0, 
            retry_interval=getattr(conn_options, "retry_interval", 0.0), 
            timeout=getattr(conn_options, "timeout", 10.0)
        )
        return self.adapter.chat(chat_ctx=chat_ctx, tools=tools, conn_options=no_retry_opts, **kwargs)


def _build_llm_fallback() -> llm.LLM:
    """
    Build the LLM chain with the most reliable/available provider first.

    Order:
      1. Groq (llama-3.3-70b-versatile)
      2. Gemini
      3. Gemini secondary model

    Gemini quota errors therefore do not block normal voice conversations
    when a working Groq key is configured.

    MODEL CHOICE: llama-3.3-70b-versatile and llama-3.1-8b-instant were
    tried here briefly to get more free-tier TPM headroom than
    openai/gpt-oss-20b's 8,000 TPM ceiling, but BOTH Llama models are now
    Enterprise-only on Groq (confirmed via a 404 model_not_found error when
    actually deployed, then confirmed again via Groq's official model list
    showing them as "Contact Sales" / no free-tier access at all).

    groq/compound-mini was tried next (70,000 TPM free-tier, per this
    account's own Organization Limits page) but was reverted in favor of
    using BOTH openai/gpt-oss-20b AND openai/gpt-oss-120b as two separate
    Groq fallback entries instead. Reasoning: compound/compound-mini are
    "agentic systems" that may use their OWN built-in tools (web search,
    code execution) alongside/instead of the custom tools this agent hands
    them, which is unpredictable behavior to debug in a voice UX. The two
    gpt-oss models are plain, predictable chat-completion models, and -
    per this account's own Limits page - each model's TPM quota is tracked
    SEPARATELY (8,000 TPM each), so stacking both here effectively gives
    16,000 TPM of combined Groq headroom before ever falling through to
    Gemini, without touching compound's uncertain tool-use behavior.
    gpt-oss-20b goes first since it's faster (~1000 tokens/sec vs 120b's
    ~500 tokens/sec) - 120b only gets used on the turns where 20b's own
    8,000 TPM bucket is already exhausted for that minute.

    To verify current numbers yourself instead of trusting old comments
    here, check console.groq.com/settings/limits directly (toggle "Show
    Current Project Limits" for your actual configured limits, which can
    differ from the org defaults shown by default).

    Ollama was previously a 4th fallback here but has been removed - it was
    never actually reachable in this deployment (every attempt logged a
    connection-refused/timeout), so it was pure dead weight adding a
    guaranteed multi-second stall to every fallback cascade that reached it,
    with zero chance of ever succeeding. Add a real, reachable local model
    back here later if one is actually running.
    """
    providers: list[llm.LLM] = []
    from openai import AsyncOpenAI

    if config.ENABLE_TOGETHER:
        logger.info("Fallback Chain: loading Together AI (60k TPM free tier)")
        providers.append(
            CooldownAwareLLM(
                openai.LLM(
                    model="meta-llama/Meta-Llama-3.1-8B-Instruct-Turbo",
                    client=AsyncOpenAI(
                        base_url="https://api.together.xyz/v1",
                        api_key=config.TOGETHER_API_KEY,
                        max_retries=0
                    )
                ),
                cooldown_seconds=60.0
            )
        )
    else:
        logger.warning("Together AI is disabled in environment config.")

    if config.GROQ_API_KEY:
        logger.info("Fallback Chain: loading Groq (8k TPM free tier)")
        providers.append(
            CooldownAwareLLM(
                openai.LLM(
                    model="openai/gpt-oss-20b",
                    client=AsyncOpenAI(
                        base_url="https://api.groq.com/openai/v1",
                        api_key=config.GROQ_API_KEY,
                        max_retries=0
                    )
                ),
                cooldown_seconds=60.0
            )
        )

    if config.GOOGLE_API_KEY:
        logger.info("Fallback Chain: loading Google Gemini (15 RPM free tier)")
        providers.append(
            SanitizedGeminiLLM(
                CooldownAwareLLM(
                    openai.LLM(
                        model="gemini-3.6-flash",
                        client=AsyncOpenAI(
                            base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
                            api_key=config.GOOGLE_API_KEY,
                            max_retries=0
                        )
                    ),
                    cooldown_seconds=60.0
                )
            )
        )

    if not providers:
        raise ValueError("No LLM providers initialized. Set GROQ_API_KEY or GOOGLE_API_KEY.")

    logger.info("LLM fallback chain initialized with %d provider(s)", len(providers))

    adapter = llm.FallbackAdapter(
        providers,
        attempt_timeout=3.5,
        max_retry_per_llm=0,  # Do not retry the same failing provider immediately
        retry_interval=0,
        retry_on_chunk_sent=False,
    )
    
    return NoRetryFallbackAdapter(adapter)


def _system_prompt() -> str:
    today_str = datetime.now().strftime("%Y-%m-%d, %A")

    return f"""
You are "{config.AGENT_NAME}", a voice agent for {config.PLATFORM_NAME}.
Today: {today_str}.

RULES:
1. ONLY help with finding/booking events on {config.PLATFORM_NAME}.
2. Use search_events FIRST to find event_ids.
   - If multiple showtimes exist, ask caller for preferred time.
   - Status: pass "Sold Out" if asked, "Upcoming" if asking for available, else leave blank.
   - For follow-ups ("the first one"), re-call search_events with previous filters.
3. Use get_ticket_categories(event_id) to check prices.
4. Use get_available_seats(event_id) ONLY for events with seat maps.
5. Use book_ticket() after user explicitly confirms event, category, and seat count.
6. Use get_booking_status() for user's existing bookings.
7. Use check_cancellation_eligibility() BEFORE cancelling. Get confirmation, then use cancel_booking().
8. Use get_buy_advice() for demand/urgency questions.
9. Use advise_seats() for seat recommendations.

CONSTRAINTS:
- NEVER invent data (event names, prices, seats).
- Maximum 25 words per turn. Keep it concise.
- Never read out the internal event_id.
- Reply in the caller's language (English, Hindi, Hinglish).
""".strip()

class ConcertVoiceAgent(Agent):
    """LiveKit 1.x Agent containing the dynamic booking toolset."""

    def __init__(
        self,
        *,
        instructions: str,
        tools: list[Any],
        greeting: str,
        chat_ctx: llm.ChatContext | None = None,
        greeting_audio: list[rtc.AudioFrame] | None = None,
        tts_english=None,
        tts_hindi=None,
    ):
        super().__init__(
            instructions=instructions,
            tools=tools,
            chat_ctx=chat_ctx,
        )
        self._greeting = greeting
        self._greeting_audio = greeting_audio
        self._tts_english = tts_english
        self._tts_hindi = tts_hindi

    async def on_enter(self) -> None:
        logger.info("Agent entered the LiveKit session; delivering greeting.")
        
        # Suppress greeting if there's already conversation history
        history_msgs = [m for m in self.chat_ctx.messages() if m.role in ("user", "assistant")]
        if len(history_msgs) > 0:
            logger.info("Existing conversation history found, skipping initial greeting.")
            return

        if self._greeting_audio:
            # Cached path: no TTS call, just replays pre-rendered frames.
            await self.session.say(
                self._greeting,
                audio=_replay_cached_audio(self._greeting_audio),
                allow_interruptions=True,
            )
        else:
            # Fallback: cache wasn't ready (e.g. first-ever synthesis failed) —
            # falls through to a live TTS call same as before.
            await self.session.say(
                self._greeting,
                allow_interruptions=True,
            )

    async def tts_node(self, text, model_settings):
        """
        Picks between a Hindi and an English Cartesia voice per response,
        mirroring tata_voice_server.py's tts_english/tts_hindi +
        _detect_hindi() pattern — while preserving streaming latency.

        Only buffers a small PREFIX of the response (until DETECT_CHARS
        chars or the first sentence-ending punctuation, whichever comes
        first) to decide the language, then opens the chosen TTS stream and
        pushes the rest of the text as it arrives from the LLM — same
        incremental push_text()/end_input() pattern as the framework's own
        Agent.default.tts_node(). This avoids waiting for the full LLM turn
        before speaking (which an earlier version of this fix did).

        Trade-off: if a reply code-switches language partway through, the
        whole utterance still plays in whichever voice the opening ~40
        chars matched (Cartesia can't switch voice mid-stream, and neither
        could the full-buffer version this replaces) — acceptable since the
        system prompt already asks the model to pick one language per turn.
        """
        if self._tts_english is None or self._tts_hindi is None:
            # Dual-TTS not configured (e.g. missing CARTESIA_API_KEY) — fall
            # back to the framework's normal streaming behavior.
            async for frame in Agent.default.tts_node(self, text, model_settings):
                yield frame
            return

        DETECT_CHARS = 40
        SENTENCE_ENDERS = (".", "!", "?", "\u0964")  # includes Hindi danda

        text_iter = text.__aiter__()
        prefix = ""
        async for chunk in text_iter:
            prefix += chunk
            if len(prefix) >= DETECT_CHARS or any(p in prefix for p in SENTENCE_ENDERS):
                break

        if not prefix.strip():
            return

        chosen_tts = self._tts_hindi if _detect_hindi(prefix) else self._tts_english
        logger.info(
            f"tts_node: routing to {'Hindi' if chosen_tts is self._tts_hindi else 'English'} "
            f"Cartesia voice (decided on first {len(prefix)} chars)"
        )

        conn_options = self.session.conn_options.tts_conn_options
        async with chosen_tts.stream(conn_options=conn_options) as stream:

            async def _forward_input() -> None:
                stream.push_text(prefix)
                async for chunk in text_iter:
                    stream.push_text(chunk)
                stream.end_input()

            forward_task = asyncio.create_task(_forward_input())
            try:
                async for ev in stream:
                    yield ev.frame
            finally:
                await utils.aio.cancel_and_wait(forward_task)


def _tool_list(toolset: Any) -> list[Any]:
    """Extract decorated FunctionTool objects from a toolset instance."""
    names = (
        "search_events",
        "get_ticket_categories",
        "get_available_seats",
        "book_ticket",
        "get_booking_status",
        "check_cancellation_eligibility",
        "cancel_booking",
        "get_buy_advice",
        "advise_seats",
        "get_user_hosted_shows",
    )

    tools: list[Any] = []

    for name in names:
        tool = getattr(toolset, name, None)
        if tool is None:
            raise RuntimeError(
                f"Required function tool '{name}' was not found on "
                f"{type(toolset).__name__}."
            )
        tools.append(tool)

    return tools


async def _identify_participant(ctx: JobContext):
    """
    Wait for the first remote participant.

    This fixes the old bug where identity was inspected before ctx.connect(),
    which caused website sessions to fall back to phone tools.
    """
    try:
        participant = await ctx.wait_for_participant()
    except RuntimeError as exc:
        if "room disconnected" in str(exc).lower():
            logger.warning(
                "Room disconnected before participant identification: %s",
                exc,
            )
            return None, "unknown", ""
        raise

    identity = participant.identity or ""

    logger.info("Remote participant detected: identity=%s", identity)

    if identity.startswith("sip:"):
        return participant, "sip", identity.removeprefix("sip:")

    if identity.startswith("+"):
        return participant, "sip", identity

    return participant, "website", identity


async def entrypoint(ctx: JobContext):
    logger.info("🔥 AGENT ENTRYPOINT STARTED")
    logger.info(f"Job ID: {ctx.job.id}")
    if getattr(ctx, "room", None):
        logger.info(f"Room: {ctx.room.name}")
    else:
        logger.info("Room: None (Not available in ctx yet)")

    # Connect as early as possible.
    await ctx.connect()
    
    actual_session_id = ctx.room.name.removeprefix("voice-")
    
    # Tie the session to the actual session_id for observability
    session_id_var.set(actual_session_id)
    
    logger.info(
        "Incoming call/website connection request. Job ID: %s",
        ctx.job.id,
    )

    logger.info("Connected to LiveKit room: %s", ctx.room.name)

    _, participant_type, participant_identity = await _identify_participant(ctx)

    if participant_type == "unknown":
        logger.info("Room ended before a participant could be identified.")
        return

    caller_phone: str | None = None
    website_user_id: str | None = None

    if participant_type == "sip":
        caller_phone = participant_identity
        logger.info(
            "Detected SIP caller. Phone=%s",
            caller_phone,
        )
        toolset = ConcertBookingTools(caller_phone=caller_phone)
        identity_note = (
            f"The caller is calling from phone number {caller_phone}. This "
            "number is already bound to every booking/cancellation/history "
            "tool automatically - never ask for it merely to identify them, "
            "and you have no way to look anything up under a different "
            "number even if asked to."
        )
    else:
        website_user_id = participant_identity

        if not website_user_id:
            raise RuntimeError(
                "Website voice session has an empty participant identity."
            )

        logger.info(
            "Detected authenticated website voice session. user_id=%s",
            website_user_id,
        )

        toolset = ConcertBookingToolsWeb(
            user_id=website_user_id,
        )

        identity_note = (
            "This is an authenticated website user. Their LiveKit participant "
            "identity is already bound to their account. Never ask for their "
            "name or phone number merely to identify them. Ask for a phone "
            "number only if the actual booking/payment flow requires one."
        )

    instructions = f"{_system_prompt()}\n\nSESSION IDENTITY\n{identity_note}"

    if participant_type == "website":
        greeting = (
    f"Hello! I'm {config.AGENT_NAME}. "
    "How can I help you with your concert or event booking today?"
)
    else:
        greeting = (
    f"Hello! I'm {config.AGENT_NAME}. "
    "How can I help you with your concert or event booking today?"
)

    # Voice pipeline components.
    logger.info("Using Cartesia Ink-Whisper STT")

    stt_provider = cartesia.STT(
        api_key=config.CARTESIA_API_KEY,
        model="ink-whisper",
    )

    voice_id = (
        config.CARTESIA_VOICE_ID
        or "c6bbc7d5-4b35-4d49-b1c6-4417019a61c1"
    )

    logger.info("Using Cartesia TTS voice=%s", voice_id)

    # Two Cartesia TTS instances (English + Hindi), picked per-response by
    # ConcertVoiceAgent.tts_node() via _detect_hindi(). Mirrors
    # tata_voice_server.py's tts_english/tts_hindi pattern — restores the
    # Hindi/Hinglish pronunciation support that was lost when this file was
    # rewritten for livekit-agents 1.7 (it was hardcoded to language="en").
    tts_english = cartesia.TTS(
        api_key=config.CARTESIA_API_KEY,
        voice=voice_id,
        language="en",
        model="sonic-2",
    )
    tts_hindi = cartesia.TTS(
        api_key=config.CARTESIA_API_KEY,
        voice=voice_id,
        language="hi",
        model="sonic-2",
    )
    # AgentSession still needs ONE tts= as its baseline/fallback (used by
    # Agent.default.tts_node() if tts_node ever falls through, and for
    # framework bookkeeping like prewarm()) — English is the safe default.
    tts_provider = tts_english

    logger.info("Loading Silero VAD")

    # min_speech_duration=0.2: ignores speech blips shorter than 200ms (mic
    # pops, breathing, background clicks). Every VAD false-trigger still gets
    # forwarded to Cartesia Ink-Whisper, which bills 1 credit per second of
    # audio SENT regardless of whether real speech was in it — this cuts
    # down on STT credits spent transcribing non-speech.
    #
    # LATENCY: min_silence_duration is a flat delay added to EVERY single
    # turn (the agent waits this long after the caller stops talking before
    # deciding they're actually done and starting to respond) - it was 0.5s,
    # meaning half a second of dead air was baked into every response no
    # matter what. Lowered to 0.35s, which still comfortably avoids cutting
    # people off mid-sentence for a normal speaking pace, while shaving a
    # noticeable, universal chunk off the "every response feels a bit slow"
    # complaint. If callers start getting cut off mid-thought, raise this
    # back up in 0.05 increments rather than jumping straight back to 0.5.
    silero_vad = silero.VAD.load(
        activation_threshold=0.6,
        min_silence_duration=0.35,
        min_speech_duration=0.2,
        prefix_padding_duration=0.3,
    )

    fallback_llm = _build_llm_fallback()

    # Render (or reuse cached) greeting audio BEFORE creating the agent —
    # this is the credit-saving step. First session in this worker process
    # pays for one real TTS call; every session after that replays the
    # cached frames for free.
    try:
        greeting_audio = await _get_cached_greeting_audio(tts_provider, greeting)
    except Exception:
        logger.exception("Greeting pre-render failed — falling back to live TTS for this session.")
        greeting_audio = None

    # Load existing text chat history
    from app.agents import memory
    history_turns = memory.load_history(
        agent="customer",
        user_id=website_user_id if participant_type == "website" else caller_phone,
        session_id=actual_session_id
    )
    
    initial_ctx = llm.ChatContext()
    initial_ctx.add_message(
        role="system",
        content=instructions,
    )
    for turn in history_turns:
        normalized_role = "assistant" if turn.role == "model" else turn.role
        if normalized_role in ("developer", "system", "user", "assistant"):
            initial_ctx.add_message(role=normalized_role, content=turn.parts[0].text)

    initial_msg_count = len(initial_ctx.messages())
    
    agent = ConcertVoiceAgent(
        instructions=instructions,
        tools=_tool_list(toolset),
        greeting=greeting,
        chat_ctx=initial_ctx,
        greeting_audio=greeting_audio,
        tts_english=tts_english,
        tts_hindi=tts_hindi,
    )

    session = AgentSession(
        vad=silero_vad,
        stt=stt_provider,
        llm=fallback_llm,
        tts=tts_provider,
        max_tool_steps=5,
    )

    session_id = actual_session_id
    session_start = datetime.now()
    transcript_messages: list[dict[str, str]] = []

    # LATENCY VISIBILITY: logs the real per-component timing LiveKit already
    # measures internally for every turn - end-of-utterance detection delay,
    # LLM time-to-first-token, and TTS time-to-first-byte. Without this, any
    # further latency tuning is guesswork; with it, the logs show exactly
    # which stage (turn detection vs LLM vs TTS vs network) is actually slow
    # on a given turn, so effort goes to the real bottleneck instead of
    # whichever component seems most suspicious. Search backend logs for
    # "[LATENCY]" to see these live during a call.
    @session.on("metrics_collected")
    def on_metrics_collected(ev):
        m = ev.metrics
        kind = type(m).__name__
        if kind == "EOUMetrics":
            logger.info(
                f"[LATENCY] end-of-utterance delay: {getattr(m, 'end_of_utterance_delay', '?')}s "
                f"(time from caller going silent to the agent deciding they're done talking)"
            )
        elif kind == "LLMMetrics":
            logger.info(
                f"[LATENCY] LLM time-to-first-token: {getattr(m, 'ttft', '?')}s | "
                f"total generation: {getattr(m, 'duration', '?')}s"
            )
        elif kind == "TTSMetrics":
            logger.info(
                f"[LATENCY] TTS time-to-first-byte: {getattr(m, 'ttfb', '?')}s | "
                f"total synthesis: {getattr(m, 'duration', '?')}s"
            )
        elif kind == "STTMetrics":
            logger.info(f"[LATENCY] STT processing duration: {getattr(m, 'duration', '?')}s")
        else:
            logger.info(f"[LATENCY] {kind}: {m}")

    @session.on("user_input_transcribed")
    def on_user_transcribed(event):
        if not event.is_final:
            return

        logger.info(
            "USER [%s]: %s",
            event.language or "unknown",
            event.transcript,
        )

    @session.on("conversation_item_added")
    def on_conversation_item(event):
        item = event.item

        try:
            role = item.role
            text = item.raw_text_content or ""
        except Exception:
            return

        if not text.strip():
            return

        speaker = "Caller" if role == "user" else "Agent"

        transcript_messages.append(
            {
                "time": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "speaker": speaker,
                "text": text,
            }
        )

        logger.info("%s: %s", speaker, text)

    @session.on("error")
    def on_session_error(event):
        logger.error(
            "AgentSession error: %s",
            getattr(event, "error", event),
        )

    logger.info("Starting LiveKit AgentSession")

    await session.start(
        agent=agent,
        room=ctx.room,
    )

    async def _save_session_on_shutdown(reason: str = ""):
        session_end = datetime.now()

        full_transcript_json = __import__("json").dumps(
            transcript_messages,
            ensure_ascii=False,
            indent=2,
        )

        plain_text = "\n".join(
            f"{m['time']} [{m['speaker']}]: {m['text']}"
            for m in transcript_messages
        )

        summary = ""
        outcome = "NO_ACTION"

        if transcript_messages:
            # Do not make another LLM request during shutdown. A summary call
            # can consume the same exhausted quota that caused the voice
            # provider fallback, and it is not necessary to persist the call.
            user_text = " ".join(
                m["text"].lower()
                for m in transcript_messages
                if m["speaker"] == "Caller"
            )

            if any(word in user_text for word in ("cancel", "cancellation", "cancelled")):
                outcome = "CANCELLED"
            elif any(word in user_text for word in ("book", "booking", "ticket", "seat")):
                outcome = "INQUIRY"
            else:
                outcome = "NO_ACTION"

            summary = (
                f"Voice booking session with {len(transcript_messages)} "
                f"conversation message(s). Outcome: {outcome}."
            )

        try:
            # Sync Voice Turns to Text DB
            if hasattr(session, 'chat_ctx') or hasattr(agent, 'chat_ctx'):
                target_ctx = getattr(agent, 'chat_ctx', None) or session.chat_ctx
                new_messages = target_ctx.messages()[initial_msg_count:]
                
                # Sanitize: only final user/assistant texts, no tool stuff
                valid_inserts = []
                for m in new_messages:
                    if m.role in ("user", "assistant") and isinstance(m, llm.ChatMessage) and m.content:
                        # Extract the string text (content can be str or list of ChatContent)
                        if isinstance(m.content, str):
                            valid_inserts.append({"role": m.role, "message": m.content})
                        elif isinstance(m.content, list):
                            text_parts = [p.text for p in m.content if hasattr(p, 'text') and p.text]
                            if text_parts:
                                valid_inserts.append({"role": m.role, "message": " ".join(text_parts)})
                                
                if valid_inserts:
                    uid = website_user_id if website_user_id else caller_phone
                    memory.save_messages("customer", uid, session_id, valid_inserts)
                    logger.info("Saved %d new voice messages to chat_history.", len(valid_inserts))
                    
            voice_db.log_call_session(
                session_id=session_id,
                caller_phone=caller_phone,
                started_at=session_start,
                ended_at=session_end,
                transcript=full_transcript_json,
                summary=summary,
                outcome=outcome,
            )

            logger.info(
                "Session '%s' saved to call_sessions. reason=%s",
                session_id,
                reason,
            )
        except Exception as exc:
            error_text = str(exc)

            if (
                "call_sessions" in error_text
                or "PGRST205" in error_text
                or "Could not find the table" in error_text
            ):
                logger.warning(
                    "Voice session was not persisted because "
                    "public.call_sessions is unavailable. "
                    "Create the table later if call-history persistence is needed. "
                    "Session=%s Error=%s",
                    session_id,
                    exc,
                )
            else:
                logger.exception(
                    "Failed to save session '%s' to call_sessions",
                    session_id,
                )

    ctx.add_shutdown_callback(_save_session_on_shutdown)


if __name__ == "__main__":
    cli.run_app(
        WorkerOptions(
            agent_name="receptionist",
            entrypoint_fnc=entrypoint,
            num_idle_processes=0,
            # load_threshold is removed to prevent false capacity rejections during local dev spikes
            job_memory_warn_mb=400,      # logs a warning before it gets fatal,
                                          # instead of a silent OOM-kill —
                                          # gives you real numbers to see how
                                          # close to the ceiling each job runs.
            job_memory_limit_mb=450,     # kills just THAT job cleanly (with a
                                          # log) instead of letting the whole
                                          # container OOM and restart — so at
                                          # least other calls aren't affected
                                          # and you get a diagnosable error.
        )
    )