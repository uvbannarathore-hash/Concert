"""
gemini_loop.py — Generic multi-turn Gemini function-calling loop, shared by
the admin and customer agents (app/agents/admin_agent.py and
app/agents/customer_agent.py).

This replaces n8n's "AI Agent" + "Google Gemini Chat Model" + "Simple
Memory" nodes. Building the conversation's Content array by hand here
(rather than going through n8n/LangChain's abstraction) is what fixes the
recurring "Please ensure that function call turn comes immediately after a
user turn or after a function response turn" 400 errors we kept hitting in
n8n. Gemini's rule is simple: a model turn containing function_call parts
must be immediately followed by ONE user turn containing ALL of the
matching function_response parts (one per call, in any order) before
anything else happens. This loop enforces that structure directly, so it
correctly handles the model requesting one tool call OR several at once
(e.g. "create all 4 of these events") without needing to prompt-engineer
the model into calling tools "one at a time" the way the n8n version had to.

Tool handler functions can be either sync or async - both are supported.
"""

import inspect
import logging
import time

from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY
from app.services.ai_service import generate_content_with_fallback

logger = logging.getLogger("gemini_loop")

# ---------------------------------------------------------------------------
# Helper to convert arbitrary argument structures into an immutable, hashable
# representation. Lists/tuples become tuples, dicts become frozensets of
# (key, value) pairs (sorted for deterministic order), and primitive types are
# returned unchanged. This ensures that the duplicate‑call tracker can safely
# store any combination of arguments, including nested lists/dicts.
# ---------------------------------------------------------------------------
from typing import Any

def _make_hashable(value: Any) -> Any:
    if isinstance(value, dict):
        return frozenset((k, _make_hashable(v)) for k, v in sorted(value.items()))
    if isinstance(value, (list, tuple, set)):
        return tuple(_make_hashable(v) for v in value)
    return value

MODEL_NAME = "gemini-3.1-flash-lite" 
MAX_TOOL_ITERATIONS = 8  # safety valve against infinite tool-call loops

_client = genai.Client(api_key=GEMINI_API_KEY)


async def run_agent(
    system_prompt: str,
    iter1_system_prompt: str,
    function_declarations: list[dict],
    tool_handlers: dict,
    history: list[types.Content],
    user_message: str,
) -> str:
    """
    Runs one full turn of the agent loop: sends the user's message (with
    prior conversation history) to Gemini, executes any tool call(s) it
    requests, feeds the result(s) back, and repeats until Gemini returns a
    plain text reply (or MAX_TOOL_ITERATIONS is hit as a safety valve).

    Returns the final text reply only. Callers are responsible for
    persisting the (user_message, reply) pair via agents/memory.py - this
    function does not know about sessions or storage.
    """
    contents = list(history) + [
        types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
    ]

    tools = types.Tool(function_declarations=function_declarations)
    # config is now created inside the loop
    
    executed_calls = set()

    import asyncio

    for _ in range(MAX_TOOL_ITERATIONS):
        try:
            rough_char_count = len(str(contents))
            
            # Use pruned prompt for Iter 1 (when _ == 0) to speed up tool selection,
            # use full prompt for Iter 2+ so it knows how to format the text reply.
            current_prompt = iter1_system_prompt if _ == 0 else system_prompt
            config = types.GenerateContentConfig(
                system_instruction=current_prompt,
                tools=[tools],
            )
            
            response = generate_content_with_fallback(
                model=MODEL_NAME,
                contents=contents,
                config=config,
            )
            
            logger.info(
                f"Gemini/Fallback API request: Iteration {_}, Context size roughly {rough_char_count} chars"
            )
        except Exception as e:
            err_str = str(e)
            logger.error(f"AI generation failed completely: {err_str}")
            return "The AI service is temporarily unavailable due to high demand. Please try again in a few moments."

        candidate = response.candidates[0]
        parts = candidate.content.parts or []
        function_calls = [p.function_call for p in parts if p.function_call]

        if not function_calls:
            final_text = "".join(p.text for p in parts if p.text)
            return final_text or "Sorry, I couldn't come up with a reply for that."

        # ALL function responses for this turn go together in ONE user-role
        # Content, immediately after the model's function-call turn. This
        # is the exact structure Gemini requires whether the model asked
        # for one tool call or several at once in the same turn.
        contents.append(candidate.content)

        response_parts = []
        for fc in function_calls:
            handler = tool_handlers.get(fc.name)
            args = dict(fc.args) if fc.args else {}

            # Normalise args into an immutable, hashable representation
            hashable_args = _make_hashable(args)
            call_signature = (fc.name, hashable_args)
            if call_signature in executed_calls:
                logger.warning(f"Model requested duplicate tool in same loop: {fc.name} args={args}")
                result = {"error": "You already called this tool with these exact arguments in this turn. Use the data from the previous response."}
            elif handler is None:
                logger.warning(f"Model requested unknown tool: {fc.name}")
                result = {"error": f"Unknown tool: {fc.name}"}
            else:
                try:
                    # Redact sensitive arguments before logging
                    safe_args = {}
                    for k, v in args.items():
                        if k.lower() in ("password", "token", "email", "phone", "jwt", "authorization", "secret", "card", "cvv"):
                            safe_args[k] = "***REDACTED***"
                        else:
                            safe_args[k] = v
                    logger.info(f"Executing tool {fc.name}", extra={"extra_data": {"tool_name": fc.name, "tool_args": safe_args}})
                    
                    tool_start = time.perf_counter()
                    if inspect.iscoroutinefunction(handler):
                        result = await handler(**args)
                    else:
                        result = handler(**args)
                    tool_latency_ms = round((time.perf_counter() - tool_start) * 1000, 2)
                    
                    logger.info(f"Tool {fc.name} completed", extra={"extra_data": {"tool_name": fc.name, "tool_latency_ms": tool_latency_ms}})
                except Exception as e:
                    tool_latency_ms = round((time.perf_counter() - tool_start) * 1000, 2) if 'tool_start' in locals() else 0
                    logger.exception(f"Tool {fc.name} raised an error", extra={"extra_data": {"tool_name": fc.name, "tool_latency_ms": tool_latency_ms}})
                    result = {"error": str(e)}
                # Record the successful (or attempted) call to prevent duplicates
                executed_calls.add(call_signature)

            response_parts.append(
                types.Part.from_function_response(name=fc.name, response={"result": result})
            )

        # ALL function responses for this turn go together in ONE user-role
        # Content, immediately after the model's function-call turn. This
        # is the exact structure Gemini requires whether the model asked
        # for one tool call or several at once in the same turn.
        contents.append(types.Content(role="user", parts=response_parts))

    return (
        "Sorry, that request needed too many steps and I couldn't finish it. "
        "Could you try rephrasing it or breaking it into smaller steps?"
    )

async def run_agent_stream(
    system_prompt: str,
    iter1_system_prompt: str,
    function_declarations: list[dict],
    tool_handlers: dict,
    history: list[types.Content],
    user_message: str,
):
    from google import genai
    from app.config import GEMINI_API_KEY
    _async_client = genai.Client(api_key=GEMINI_API_KEY)
    
    contents = list(history) + [
        types.Content(role="user", parts=[types.Part.from_text(text=user_message)])
    ]
    tools = types.Tool(function_declarations=function_declarations)
    executed_calls = set()
    import asyncio

    for _ in range(MAX_TOOL_ITERATIONS):
        try:
            current_prompt = iter1_system_prompt if _ == 0 else system_prompt
            config = types.GenerateContentConfig(
                system_instruction=current_prompt,
                tools=[tools],
            )
            
            if _ > 0:
                # ITER-2: stream the final text response
                try:
                    async for chunk in await _async_client.aio.models.generate_content_stream(
                        model=MODEL_NAME,
                        contents=contents,
                        config=config
                    ):
                        if chunk.text:
                            yield chunk.text
                    return
                except Exception as stream_e:
                    logger.warning(f"Streaming failed, falling back to blocking. Error: {stream_e}")
                    pass # Fall back to blocking below
            
            response = generate_content_with_fallback(
                model=MODEL_NAME,
                contents=contents,
                config=config,
            )
        except Exception as e:
            err_str = str(e)
            logger.error(f"AI generation failed completely: {err_str}")
            yield "The AI service is temporarily unavailable due to high demand. Please try again in a few moments."
            return

        candidate = response.candidates[0]
        parts = candidate.content.parts or []
        function_calls = [p.function_call for p in parts if p.function_call]

        if not function_calls:
            final_text = "".join(p.text for p in parts if p.text)
            yield final_text or "Sorry, I couldn't come up with a reply for that."
            return

        contents.append(candidate.content)

        response_parts = []
        for fc in function_calls:
            handler = tool_handlers.get(fc.name)
            args = dict(fc.args) if fc.args else {}
            hashable_args = _make_hashable(args)
            call_signature = (fc.name, hashable_args)
            if call_signature in executed_calls:
                result = {"error": "You already called this tool with these exact arguments in this turn. Use the data from the previous response."}
            elif handler is None:
                result = {"error": f"Unknown tool: {fc.name}"}
            else:
                try:
                    if inspect.iscoroutinefunction(handler):
                        result = await handler(**args)
                    else:
                        result = handler(**args)
                except Exception as e:
                    result = {"error": str(e)}
                executed_calls.add(call_signature)

            response_parts.append(
                types.Part.from_function_response(name=fc.name, response={"result": result})
            )
            
        contents.append(types.Content(role="user", parts=response_parts))

    yield "Sorry, I had to stop because I was using too many tools."