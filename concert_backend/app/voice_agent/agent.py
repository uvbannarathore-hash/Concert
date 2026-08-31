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
from datetime import datetime
from typing import Any

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

    if config.GROQ_API_KEY:
        logger.info("Fallback Chain: loading Groq providers FIRST (openai/gpt-oss-20b, then openai/gpt-oss-120b)")
        providers.append(
            openai.LLM(
                model="openai/gpt-oss-20b",
                base_url="https://api.groq.com/openai/v1",
                api_key=config.GROQ_API_KEY,
            )
        )
        providers.append(
            openai.LLM(
                model="openai/gpt-oss-120b",
                base_url="https://api.groq.com/openai/v1",
                api_key=config.GROQ_API_KEY,
            )
        )

    if config.GOOGLE_API_KEY:
        logger.info("Fallback Chain: loading Google Gemini provider")
        gemini_base_url = (
            "https://generativelanguage.googleapis.com/v1beta/openai/"
        )

        providers.append(
            openai.LLM(
                model="gemini-3.7-flash",
                base_url=gemini_base_url,
                api_key=config.GOOGLE_API_KEY,
            )
        )

        providers.append(
            openai.LLM(
                model="gemini-3.5-flash",
                base_url=gemini_base_url,
                api_key=config.GOOGLE_API_KEY,
            )
        )

    if not providers:
        raise ValueError(
            "No LLM providers initialized. Set GROQ_API_KEY or GOOGLE_API_KEY."
        )

    logger.info(
        "LLM fallback chain initialized with %d provider(s)",
        len(providers),
    )

    return llm.FallbackAdapter(
        providers,
        # LATENCY: this was 8.0s - if the primary provider (Groq) is ever
        # slow to respond or briefly unavailable, the caller would sit in
        # silence for up to 8 full seconds before the agent even tried
        # falling back to Gemini. 3.5s still gives a normal Groq response
        # plenty of room (it's typically sub-second), but fails over much
        # faster on the turns where it isn't, instead of stalling the whole
        # conversation.
        attempt_timeout=3.5,
        max_retry_per_llm=0,
        retry_interval=0.25,
        retry_on_chunk_sent=False,
    )


def _system_prompt() -> str:
    today_str = datetime.now().strftime("%Y-%m-%d, %A")

    return f"""
You are a professional, friendly voice booking agent named "{config.AGENT_NAME}"
for {config.PLATFORM_NAME}, a concert/event ticket booking service.

Today is {today_str}.

YOUR ONLY ROLE
1. Find events. Use search_events with the artist/event name and/or city.
   Always search before assuming an event_id.
2. Check ticket categories, prices and availability. Use
   get_ticket_categories with the event_id returned by search_events.
3. Book tickets. Collect the event_id, exact ticket category, seat count,
   and all information required by the active booking tool. Always confirm
   the event, category and seat count before booking.
4. Check existing booking status using get_booking_status.
5. Cancel a booking only after obtaining and confirming the exact booking_id.

BOOKING SAFETY
- Never invent event names, event IDs, prices, seat availability or booking IDs.
- Always use the tools to verify current data.
- Never call book_ticket until the user has explicitly confirmed the final
  event, category and number of seats.
- Explain that a booking is Pending until payment is completed through the
  payment/SMS flow when that is what the booking tool reports.
- If a tool reports failure, clearly explain the returned reason.

CONVERSATION STYLE
- Keep responses concise and natural for voice.
- HARD LIMIT: never speak more than 25 words in a single turn. TTS is billed
  per character spoken, so a long answer directly costs more — say the most
  important part now and let the caller ask a follow-up if they want more.
- Do not give long explanations unless necessary.
- Stay strictly focused on concert/event ticket booking.
- Do not claim to browse the internet or discuss internal implementation.
- If asked about unrelated topics, briefly redirect to event/ticket booking.

LANGUAGE
- Reply in the same language used by the caller.
- For Hindi, reply in Hindi/Devanagari.
- For English, reply in English.
- For Hinglish, naturally match the user's Hinglish style.
""".strip()


class ConcertVoiceAgent(Agent):
    """LiveKit 1.x Agent containing the dynamic booking toolset."""

    def __init__(
        self,
        *,
        instructions: str,
        tools: list[Any],
        greeting: str,
        greeting_audio: list[rtc.AudioFrame] | None = None,
        tts_english=None,
        tts_hindi=None,
    ):
        super().__init__(
            instructions=instructions,
            tools=tools,
        )
        self._greeting = greeting
        self._greeting_audio = greeting_audio
        self._tts_english = tts_english
        self._tts_hindi = tts_hindi

    async def on_enter(self) -> None:
        logger.info("Agent entered the LiveKit session; delivering greeting.")

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
        "book_ticket",
        "get_booking_status",
        "cancel_booking",
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
    logger.info(
        "Incoming call/website connection request. Job ID: %s",
        ctx.job.id,
    )

    # Connect as early as possible.
    await ctx.connect()
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
        toolset = ConcertBookingTools()
        identity_note = (
            f"The caller is calling from phone number {caller_phone}. "
            "You may use this phone number for booking tools, but confirm "
            "important booking details before booking."
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
            f"Namaste! Main {config.AGENT_NAME} hoon. "
            "Kaunsa concert ya event book karna hai?"
        )
    else:
        greeting = (
            f"Namaste! Main {config.AGENT_NAME} hoon. "
            "Kaunsa concert ya event book karna hai?"
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

    agent = ConcertVoiceAgent(
        instructions=instructions,
        tools=_tool_list(toolset),
        greeting=greeting,
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

    session_id = ctx.room.name
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
            entrypoint_fnc=entrypoint,
        )
    )