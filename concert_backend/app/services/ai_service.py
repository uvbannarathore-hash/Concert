import os
import json
import time
import logging
from typing import Optional, List, Dict, Any, Union
from google import genai
from google.genai import types
from groq import Groq

logger = logging.getLogger("ai_service")

# Initialize clients
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
gemini_client = genai.Client(api_key=GEMINI_API_KEY)

GROQ_API_KEY = os.getenv("GROQ_API_KEY")
groq_client = Groq(api_key=GROQ_API_KEY, max_retries=0)

GROQ_FALLBACK_MODEL = os.getenv("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")
GROQ_MAX_INPUT_TOKENS = int(os.getenv("GROQ_MAX_INPUT_TOKENS", "2200"))

COMPACT_CUSTOMER_PROMPT = """You are LiveWire's concise booking assistant.
DOMAIN: ONLY answer queries about events/tickets/bookings. Reject all out-of-domain queries.
PERSONALIZATION: Address user by first name if in [User name: X].
ADMINS: If [User is_admin: true], NEVER book tickets. Tell them to use a regular account.
ACCOUNT LINKING (Telegram only): If user asks to link website account, ask for email and use link_telegram_account.

TOOLS & ROUTING (CRITICAL):
- search_events: ALWAYS use to find events/availability. If multiple showtimes exist, ASK which time.
- get_ticket_categories: Use for prices/categories.
- get_available_seats: Use AFTER get_ticket_categories if has_seat_map is true. NEVER infer has_seat_map; trust tool output. Never invent seat numbers.
- get_buy_advice: Use for ticket demand questions.
- advise_seats: Use for seat recommendations.
- get_user_booking_history: Use for all past bookings.
- book_ticket_transaction: Use ONLY after user confirms summary.
- check_cancellation_eligibility & cancel_booking: For cancellations.
- Upgrade/Downgrade: request_seat_upgrade, direct_seat_downgrade, approve_seat_upgrade.
- Group Bookings: initiate_group_booking, check_group_booking_status, finalize_group_booking, cancel_group_booking.
- PLAN MY NIGHT: search_events -> restaurant_suggestions -> maps_directions -> build_itinerary.

FORMATTING & RESPONSE RULES (STRICTLY FOLLOW):
- NEVER USE MARKDOWN TABLES. Do not generate |---|---| style tables anywhere.
- DATE FILTERS: When a user asks for "upcoming events", DO NOT restrict to "this month" unless explicitly requested. Return ALL future events from the tool output.
- For event lists, use exactly this format separated by a blank line:
  **Event Name**
  📅 Date & Time
  📍 Venue
  🎟️ Ticket categories with prices
  🪑 Seat Map: Available / Not available
- For seat maps, use readable bullets. NEVER invent or infer rows/seats. Use ONLY get_available_seats output:
  **[Event Name] Seat Map**
  
  🟣 [Category Name]
  • Row A: A1, A2, A3
  • Row B: B1, B2
- For simple answers, use short paragraphs or bullets.
- Answer the user's exact question FIRST, then provide supporting details concisely.
- Bold event names and important values.
- Use the ₹ symbol for prices (e.g. ₹5,000).
- Format dates and times consistently.
- NEVER invent information, metrics, rules, or session IDs. Use tool results as the absolute source of truth.
- If a tool fails, inform the user."""

def _extract_json_from_text(text: str) -> str:
    """Extracts JSON from text, handling markdown code blocks."""
    if not text:
        return text
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    return text.strip()

def _translate_to_groq_messages(contents, system_instruction=None) -> List[Dict[str, Any]]:
    messages = []
    
    if system_instruction:
        # system_instruction can be a string or a Content/Part object depending on caller
        sys_text = system_instruction
        if hasattr(system_instruction, "parts"):
            sys_text = "".join(p.text for p in system_instruction.parts if p.text)
        elif isinstance(system_instruction, list):
            sys_text = "".join(p.text for p in system_instruction if hasattr(p, "text") and p.text)
            
        messages.append({"role": "system", "content": str(sys_text)})

    if isinstance(contents, str):
        messages.append({"role": "user", "content": contents})
    elif isinstance(contents, list):
        for content in contents:
            # Handle genai Content objects
            if hasattr(content, "role"):
                role = "user" if content.role == "user" else "assistant"
                if content.parts:
                    # Collect text parts
                    text_parts = [p.text for p in content.parts if p.text]
                    if text_parts:
                        messages.append({"role": role, "content": "\n".join(text_parts)})
                    
                    # Handle tool calls in history
                    function_calls = [p.function_call for p in content.parts if p.function_call]
                    if function_calls:
                        tool_calls = []
                        for fc in function_calls:
                            tool_calls.append({
                                "id": f"call_{fc.name}",
                                "type": "function",
                                "function": {
                                    "name": fc.name,
                                    "arguments": json.dumps(fc.args) if fc.args else "{}"
                                }
                            })
                        messages.append({
                            "role": role,
                            "content": None,
                            "tool_calls": tool_calls
                        })
                    
                    # Handle function responses in history
                    function_responses = [p.function_response for p in content.parts if p.function_response]
                    if function_responses:
                        for fr in function_responses:
                            # Groq requires role "tool" for tool responses
                            messages.append({
                                "role": "tool",
                                "tool_call_id": f"call_{fr.name}",
                                "name": fr.name,
                                "content": json.dumps(fr.response) if fr.response else "{}"
                            })
            else:
                messages.append({"role": "user", "content": str(content)})
    else:
        messages.append({"role": "user", "content": str(contents)})
        
    return messages

def _clean_schema(schema: Any, is_optional: bool = False) -> Any:
    """Recursively converts Gemini SDK types/enums to standard JSON Schema types."""
    if isinstance(schema, dict):
        cleaned = {}
        required_fields = schema.get('required', [])
        
        for k, v in schema.items():
            if k == 'properties' and isinstance(v, dict):
                cleaned[k] = {
                    prop_name: _clean_schema(
                        prop_val, 
                        is_optional=(prop_name not in required_fields)
                    ) 
                    for prop_name, prop_val in v.items()
                }
            elif k == 'type' and v is not None:
                if hasattr(v, 'name'):
                    cleaned[k] = v.name.lower()
                elif isinstance(v, str):
                    cleaned[k] = v.lower()
                else:
                    cleaned[k] = v
            elif k == 'items':
                cleaned[k] = _clean_schema(v)
            else:
                cleaned[k] = _clean_schema(v) if isinstance(v, (dict, list)) else v
                
        if is_optional and 'type' in cleaned:
            any_of = [{k: v for k, v in cleaned.items()}]
            any_of.append({'type': 'null'})
            return {'anyOf': any_of}
            
        # Optional aggressive minification
        if getattr(_clean_schema, "minify", False):
            cleaned.pop("description", None)
            cleaned.pop("title", None)
            cleaned.pop("default", None)
            cleaned.pop("examples", None)
            
        return cleaned
    elif isinstance(schema, list):
        return [_clean_schema(item, is_optional) for item in schema]
    else:
        return schema

def _estimate_tokens(text: Any) -> int:
    """Conservative token estimator: ~3 characters per token for JSON/text."""
    if not text:
        return 0
    if isinstance(text, (dict, list)):
        text = json.dumps(text, separators=(',', ':'))
    return max(1, len(str(text)) // 3)

def _trim_payload(messages: List[Dict[str, Any]], groq_tools: Optional[List[Dict[str, Any]]]) -> List[Dict[str, Any]]:
    """
    Trims conversation history & massive tool results if total estimated tokens exceed GROQ_MAX_INPUT_TOKENS.
    Preserves system instructions, tool definitions, and the latest user query.
    """
    tool_tokens = _estimate_tokens(groq_tools) if groq_tools else 0
    
    system_msgs = [m for m in messages if m.get('role') == 'system']
    sys_tokens = sum(_estimate_tokens(m) for m in system_msgs)
    
    base_tokens = tool_tokens + sys_tokens
    budget_for_history = max(0, GROQ_MAX_INPUT_TOKENS - base_tokens)
    
    non_system = [m for m in messages if m.get('role') != 'system']
    
    if not non_system:
        return system_msgs
        
    # Chunk non-system messages into turns starting with each user message
    turns = []
    current_turn = []
    for m in non_system:
        if m.get('role') == 'user':
            if current_turn:
                turns.append(current_turn)
            current_turn = [m]
        else:
            current_turn.append(m)
    if current_turn:
        turns.append(current_turn)
        
    kept_turns = []
    current_history_tokens = 0
    
    # Always keep the last turn (current user query / latest tool results)
    last_turn = turns.pop()
    
    # If the current request explicitly focuses on a seat map (e.g., getting specific seat details),
    # aggressively drop older history right now since they use massive token limits.
    if groq_tools is not None and any("get_available_seats" in str(m) for m in last_turn):
        turns = [] # Force discard of older turns
        
    last_turn_tokens = sum(_estimate_tokens(m) for m in last_turn)
    
    # If the last turn alone exceeds the remaining budget, intelligently truncate it
    if last_turn_tokens > budget_for_history:
        for m in reversed(last_turn):
            # Truncate massive tool responses first
            if m.get('role') == 'tool' and m.get('content'):
                content_str = str(m['content'])
                if len(content_str) > 1000:
                    m['content'] = content_str[:1000] + "... [Truncated to fit budget]"
                    last_turn_tokens = sum(_estimate_tokens(mt) for mt in last_turn)
                    if last_turn_tokens <= budget_for_history:
                        break
            # Truncate massive user queries if absolutely necessary
            elif m.get('role') == 'user' and m.get('content'):
                content_str = str(m['content'])
                if len(content_str) > 2000:
                    m['content'] = content_str[:2000] + "... [Truncated to fit budget]"
                    last_turn_tokens = sum(_estimate_tokens(mt) for mt in last_turn)
                    if last_turn_tokens <= budget_for_history:
                        break
                        
    kept_turns.insert(0, last_turn)
    current_history_tokens += last_turn_tokens
    
    # Greedily keep older turns from recent to oldest
    retained_history_turns = 0
    while turns:
        older_turn = turns.pop()
        turn_tokens = sum(_estimate_tokens(m) for m in older_turn)
        if current_history_tokens + turn_tokens > budget_for_history:
            logger.warning(f"Dropping older history turn (~{turn_tokens} tokens) to respect Groq budget.")
            break 
        kept_turns.insert(0, older_turn)
        current_history_tokens += turn_tokens
        retained_history_turns += 1
        
    final_messages = system_msgs.copy()
    for t in kept_turns:
        final_messages.extend(t)
        
    logger.info(f"Fallback budget: estimated ~{base_tokens + current_history_tokens}/{GROQ_MAX_INPUT_TOKENS} tokens. (Tools: ~{tool_tokens}, Sys: ~{sys_tokens}, Hist: ~{current_history_tokens}, Turns retained: {retained_history_turns})")
    
    return final_messages

def _translate_tools(config: types.GenerateContentConfig) -> Optional[List[Dict[str, Any]]]:
    if not config or not config.tools:
        return None
        
    groq_tools = []
    for tool in config.tools:
        if hasattr(tool, "function_declarations") and tool.function_declarations:
            for fn in tool.function_declarations:
                # Need to convert dict/schema to Groq format
                groq_tool = {
                    "type": "function",
                    "function": {
                        "name": fn.name,
                        "description": fn.description or "",
                    }
                }
                
                # Parameters might be dict or Pydantic/Schema object
                params = fn.parameters
                if hasattr(params, "model_dump"):
                    params = params.model_dump(exclude_none=True)
                elif hasattr(params, "dict"):
                    params = params.dict(exclude_none=True)
                elif isinstance(params, dict):
                    params = params
                else:
                    params = None
                    
                if params:
                    groq_tool["function"]["parameters"] = _clean_schema(params)
                else:
                    groq_tool["function"]["parameters"] = {"type": "object", "properties": {}}
                    
                groq_tools.append(groq_tool)
                
    if groq_tools and getattr(_clean_schema, "minify", False):
        # Also drop top-level descriptions
        for t in groq_tools:
            if "function" in t:
                t["function"].pop("description", None)
                
    if groq_tools:
        logger.debug(f"Translated tools for Groq: {json.dumps(groq_tools)}")
                
    return groq_tools if groq_tools else None

class MockGenerateContentResponse:
    def __init__(self, candidates, text):
        self.candidates = candidates
        self._text = text
        
    @property
    def text(self):
        if self._text:
            return self._text
        if self.candidates and self.candidates[0].content.parts:
            return "".join(p.text for p in self.candidates[0].content.parts if p.text)
        return ""

def generate_content_with_fallback(model: str, contents, config: Optional[types.GenerateContentConfig] = None) -> Union[types.GenerateContentResponse, MockGenerateContentResponse]:
    """
    Centralized fallback handler. 
    Flow: Gemini -> Retry Gemini ONCE immediately -> Groq Fallback
    """
    import uuid
    request_id = str(uuid.uuid4())
    start_time = time.perf_counter()
    gemini_attempts = 0
    gemini_last_error = ""
    
    # 1. Primary: Gemini
    for attempt in range(2):
        gemini_attempts += 1
        try:
            response = gemini_client.models.generate_content(
                model=model,
                contents=contents,
                config=config
            )
            latency = round((time.perf_counter() - start_time) * 1000, 2)
            logger.info("AI Request Succeeded", extra={
                "provider": "gemini",
                "fallback": False,
                "latency_ms": latency,
                "gemini_attempts": gemini_attempts,
                "request_id": request_id
            })
            return response
        except Exception as e:
            if attempt == 0:
                logger.warning(f"Gemini failed (attempt 1), retrying immediately. Error: {str(e)}")
                continue # Retry immediately
            else:
                gemini_last_error = str(e)
                logger.warning(f"Gemini failed (attempt 2). Exhausted retries. Error: {gemini_last_error}")
                break

    # 2. Fallback: Groq
    fallback_start = time.perf_counter()
    try:
        sys_instr = config.system_instruction if config else None
        
        # If structured JSON is requested, append schema instructions to the system prompt
        response_format = None
        if config and config.response_mime_type == "application/json":
            response_format = {"type": "json_object"}
            schema_info = ""
            if config.response_schema:
                schema_info = f"\\n\\nYou MUST return valid JSON matching this schema: {config.response_schema}"
            
            if sys_instr:
                if isinstance(sys_instr, str):
                    sys_instr += schema_info
            else:
                sys_instr = f"You MUST return valid JSON.{schema_info}"

        messages = _translate_to_groq_messages(contents, sys_instr)
        groq_tools = _translate_tools(config)
        
        # Always use the concise system prompt for Groq
        for m in messages:
            if m.get('role') == 'system' and isinstance(m.get('content'), str):
                if "friendly and helpful ticket booking assistant" in m['content'].lower():
                    m['content'] = COMPACT_CUSTOMER_PROMPT + (schema_info if response_format else "")
                else:
                    m['content'] = " ".join(m['content'].split())
                    
        # Filter tools to reduce overhead based on current query context
        latest_query = ""
        last_tool_name = None
        for m in reversed(messages):
            if m.get('role') == 'user' and m.get('content'):
                latest_query = str(m['content']).lower()
                break
            elif m.get('role') == 'tool' and m.get('name') and not last_tool_name:
                last_tool_name = m.get('name')
                
        # Simple word boundaries for heuristic
        query_words = set(latest_query.replace('?', ' ').replace(',', ' ').replace('.', ' ').split())
        
        needs_booking = bool(query_words & {"book", "buy", "ticket", "tickets", "reserve", "get", "purchase", "checkout", "price", "cost", "how", "much", "category", "vip", "general"})
        needs_seat_map = bool(query_words & {"seat", "seats", "row", "front", "back", "next", "together", "which"})
                
        # INTENT-AWARE FALLBACK WORKFLOW
        # If the latest message is a tool response for simple deterministic intents, format it directly to save TPM.
        last_msg = messages[-1] if messages else {}
        is_tool_response = last_msg.get('role') == 'tool'
        
        if is_tool_response:
            try:
                tool_data = json.loads(last_msg['content'])
                if last_tool_name == "search_events" and not needs_booking and not needs_seat_map:
                    if tool_data.get("success") and tool_data.get("events"):
                        formatted_lines = []
                        for r in tool_data["events"]:
                            has_map_str = "Available" if "has_seat_map: true" in tool_data.get("message", "") else "Not available"
                            cats = r.get("ticket_categories") or []
                            cat_details = ", ".join(f"{c['category']}: ₹{c['price_inr']:,.0f}" for c in cats if c.get("price_inr") is not None)
                            price_str = cat_details if cat_details else "Price TBA"
                            formatted_lines.append(f"**{r['artist_name']}**\n📅 {r['event_date']} at {r.get('event_time', 'time TBA')}\n📍 {r['venue_name']}, {r['city']}\n🎟️ {price_str}\n🪑 Seat Map: {has_map_str}")
                        
                        final_text = "\n\n".join(formatted_lines)
                        
                        logger.info("Fallback workflow | intent=EVENT_SEARCH | ai_calls=1 | tools=1 | response_mode=format_only", extra={
                            "provider": "groq",
                            "fallback": True,
                            "fallback_reason": gemini_last_error,
                            "intent": "EVENT_SEARCH",
                            "number_of_ai_calls": 1,
                            "tools_executed": 1,
                            "estimated_tokens": 0,
                            "final_response_mode": "format_only",
                            "request_id": request_id,
                        })
                        
                        return MockGenerateContentResponse(
                            candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part.from_text(text=final_text)]))],
                            text=final_text
                        )
                        
                elif last_tool_name == "get_available_seats" and not needs_booking:
                    if tool_data.get("has_seat_map") and tool_data.get("available_seats"):
                        seats = tool_data["available_seats"]
                        by_cat = {}
                        for s in seats:
                            cat = s.get("category", "General")
                            row = s.get("seat_row", "")
                            num = s.get("seat_number", "")
                            if cat not in by_cat: by_cat[cat] = {}
                            if row not in by_cat[cat]: by_cat[cat][row] = []
                            by_cat[cat][row].append(str(num))
                            
                        event_name = "Event"
                        for m in reversed(messages):
                            if m.get('role') == 'tool' and m.get('name') == 'search_events':
                                try:
                                    search_data = json.loads(m['content'])
                                    if search_data.get('events'):
                                        event_name = search_data['events'][0]['artist_name']
                                        break
                                except:
                                    pass
                                    
                        final_text = f"**{event_name} Seat Map**\n\n"
                        for cat, rows in by_cat.items():
                            emoji = "🟣" if "royal" in cat.lower() else ("🟠" if "executive" in cat.lower() else "🟢")
                            final_text += f"{emoji} {cat.upper()}\n"
                            for row, nums in sorted(rows.items()):
                                final_text += f"• Row {row}: {', '.join(sorted(nums))}\n"
                            final_text += "\n"
                            
                        final_text = final_text.strip()
                        
                        logger.info("Fallback workflow | intent=SEAT_MAP | ai_calls=1 | tools=1 | response_mode=format_only", extra={
                            "provider": "groq",
                            "fallback": True,
                            "fallback_reason": gemini_last_error,
                            "intent": "SEAT_MAP",
                            "number_of_ai_calls": 1,
                            "tools_executed": 1,
                            "estimated_tokens": 0,
                            "final_response_mode": "format_only",
                            "request_id": request_id,
                        })
                        
                        return MockGenerateContentResponse(
                            candidates=[types.Candidate(content=types.Content(role="model", parts=[types.Part.from_text(text=final_text)]))],
                            text=final_text
                        )
            except Exception as e:
                logger.warning(f"Failed to apply deterministic formatting, falling back to Groq generation. Error: {e}")
                
        if latest_query and groq_tools:
            allowed_tools = set()
            
            if last_tool_name == "search_events" and not needs_booking and not needs_seat_map:
                allowed_tools = set()
            elif last_tool_name == "get_available_seats" and not needs_booking:
                allowed_tools = set()
            elif not needs_booking and not needs_seat_map and last_tool_name is None:
                allowed_tools = set(["search_events"])
            elif needs_seat_map and not needs_booking:
                allowed_tools = set(["search_events", "get_ticket_categories", "get_available_seats"])
            else:
                allowed_tools = set(["search_events"])
                if needs_booking or needs_seat_map or last_tool_name in ["search_events", "get_ticket_categories", "get_available_seats"]:
                    allowed_tools.update(["get_ticket_categories", "get_available_seats", "advise_seats", "book_ticket_transaction", "get_buy_advice"])
                    
                if bool(query_words & {"history", "past", "my"}):
                    allowed_tools.add("get_user_booking_history")
                    
                if bool(query_words & {"group", "friend", "friends", "invite", "rsvp"}):
                    allowed_tools.update(["initiate_group_booking", "check_group_booking_status", "finalize_group_booking", "cancel_group_booking"])
                    
                if bool(query_words & {"upgrade", "downgrade", "change"}):
                    allowed_tools.update(["request_seat_upgrade", "direct_seat_downgrade", "approve_seat_upgrade"])
                    
                if bool(query_words & {"plan", "night", "dinner", "restaurant", "restaurants", "eat", "food", "directions"}):
                    allowed_tools.update(["restaurant_suggestions", "maps_directions", "build_itinerary", "save_itinerary"])
                    
                if bool(query_words & {"cancel", "refund"}):
                    allowed_tools.update(["check_cancellation_eligibility", "cancel_booking"])
                
            groq_tools = [t for t in groq_tools if t["function"]["name"] in allowed_tools]

        # Check base tokens and minify if needed
        base_est = _estimate_tokens(groq_tools) + sum(_estimate_tokens(m) for m in messages if m.get('role') == 'system')
        if base_est > GROQ_MAX_INPUT_TOKENS * 0.8:
            logger.warning(f"Base payload is massive (Original Estimate: ~{base_est}). Minifying tools and system prompt.")
            _clean_schema.minify = True
            
            # Re-translate and re-filter with minification enabled
            all_minified_tools = _translate_tools(config)
            if all_minified_tools and latest_query:
                groq_tools = [t for t in all_minified_tools if t["function"]["name"] in allowed_tools]
            else:
                groq_tools = all_minified_tools
                
            _clean_schema.minify = False
            
            # Re-calculate AFTER minification
            base_est_after = _estimate_tokens(groq_tools) + sum(_estimate_tokens(m) for m in messages if m.get('role') == 'system')
            logger.info(f"Minified Estimate: ~{base_est_after}")
            
            if base_est_after > GROQ_MAX_INPUT_TOKENS:
                raise Exception(f"Estimated base payload ({base_est_after}) exceeds safe budget ({GROQ_MAX_INPUT_TOKENS}) even after minification.")
                    
        messages = _trim_payload(messages, groq_tools)
        
        groq_kwargs = {
            "model": GROQ_FALLBACK_MODEL,
            "messages": messages,
        }
        if groq_tools:
            groq_kwargs["tools"] = groq_tools
        if response_format:
            groq_kwargs["response_format"] = response_format
            
        try:
            groq_response = groq_client.chat.completions.create(**groq_kwargs)
            active_model = GROQ_FALLBACK_MODEL
        except Exception as e:
            logger.warning(f"Groq {GROQ_FALLBACK_MODEL} failed. Exhausted retries. Error: {str(e)}")
            raise e
        
        choice = groq_response.choices[0]
        
        # Build mocked Gemini Response
        parts = []
        if choice.message.content:
            content_str = choice.message.content
            # Validate JSON if required
            if config and config.response_mime_type == "application/json":
                content_str = _extract_json_from_text(content_str)
                try:
                    json.loads(content_str)
                except json.JSONDecodeError as je:
                    raise Exception(f"Groq returned malformed JSON: {str(je)}\\nContent: {content_str}")
            
            parts.append(types.Part.from_text(text=content_str))
            
        if choice.message.tool_calls:
            for tc in choice.message.tool_calls:
                args = json.loads(tc.function.arguments) if tc.function.arguments else {}
                fc = types.FunctionCall(name=tc.function.name, args=args)
                parts.append(types.Part(function_call=fc))
                
        candidate = types.Candidate(content=types.Content(role="model", parts=parts))
        
        mock_response = MockGenerateContentResponse(
            candidates=[candidate],
            text=choice.message.content if not (config and config.response_mime_type == "application/json") else parts[0].text if parts else ""
        )
        
        latency = round((time.perf_counter() - fallback_start) * 1000, 2)
        total_latency = round((time.perf_counter() - start_time) * 1000, 2)
        
        # Calculate final tokens for logging
        tool_tokens = _estimate_tokens(groq_tools) if groq_tools else 0
        system_tokens = sum(_estimate_tokens(m) for m in messages if m.get('role') == 'system')
        history_tokens = sum(_estimate_tokens(m) for m in messages if m.get('role') != 'system')
        estimated_tokens = tool_tokens + system_tokens + history_tokens
        selected_tools = [t["function"]["name"] for t in groq_tools] if groq_tools else []
        
        logger.info(
            f"AI Request Succeeded (Fallback) | provider=groq model={active_model} fallback_reason={gemini_last_error} | "
            f"Tokens: ~{estimated_tokens} (tools:{tool_tokens} sys:{system_tokens} hist:{history_tokens}) | Tools: {len(selected_tools)}",
            extra={
                "provider": "groq",
                "fallback": True,
                "fallback_reason": gemini_last_error,
                "latency_ms": total_latency,
                "groq_latency_ms": latency,
                "gemini_attempts": gemini_attempts,
                "request_id": request_id,
                "model": active_model,
                "estimated_tokens": estimated_tokens,
                "tool_tokens": tool_tokens,
                "system_tokens": system_tokens,
                "history_tokens": history_tokens,
                "selected_tools": selected_tools
            }
        )
        
        return mock_response
        
    except Exception as e:
        latency = round((time.perf_counter() - start_time) * 1000, 2)
        logger.error(f"AI Request Failed (Both Gemini and Groq failed). Groq Error: {str(e)}", extra={
            "provider": "groq",
            "fallback": True,
            "fallback_reason": gemini_last_error,
            "latency_ms": latency,
            "gemini_attempts": gemini_attempts,
            "request_id": request_id
        })
        # Propagate the final exception to the caller's graceful degradation layer
        raise Exception(f"Primary and Fallback AI providers failed. Last error: {str(e)}")
