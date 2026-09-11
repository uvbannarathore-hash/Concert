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

from google import genai
from google.genai import types

from app.config import GEMINI_API_KEY

logger = logging.getLogger("gemini_loop")

MODEL_NAME = "gemini-3.1-flash-lite"
MAX_TOOL_ITERATIONS = 8  # safety valve against infinite tool-call loops

_client = genai.Client(api_key=GEMINI_API_KEY)


async def run_agent(
    system_prompt: str,
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
    config = types.GenerateContentConfig(
        system_instruction=system_prompt,
        tools=[tools],
    )

    for _ in range(MAX_TOOL_ITERATIONS):
        response = _client.models.generate_content(
            model=MODEL_NAME,
            contents=contents,
            config=config,
        )

        candidate = response.candidates[0]
        parts = candidate.content.parts or []
        function_calls = [p.function_call for p in parts if p.function_call]

        if not function_calls:
            final_text = "".join(p.text for p in parts if p.text)
            return final_text or "Sorry, I couldn't come up with a reply for that."

        # The model's turn (including its function_call part(s)) must be
        # appended before the function_response turn that answers it.
        contents.append(candidate.content)

        response_parts = []
        for fc in function_calls:
            handler = tool_handlers.get(fc.name)
            args = dict(fc.args) if fc.args else {}

            if handler is None:
                logger.warning(f"Model requested unknown tool: {fc.name}")
                result = {"error": f"Unknown tool: {fc.name}"}
            else:
                try:
                    logger.info(f"Executing tool {fc.name} args={args}")
                    if inspect.iscoroutinefunction(handler):
                        result = await handler(**args)
                    else:
                        result = handler(**args)
                except Exception as e:
                    logger.exception(f"Tool {fc.name} raised an error")
                    result = {"error": str(e)}

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