"""
memory.py — Persistent conversation memory for the native Python AI agents,
backed by Supabase tables.

Customer:
- chat_history
- user_id

Admin:
- admin_chat_history
- admin_user_id

Only the final user message and final assistant reply of each turn are
persisted. Intermediate tool-call/tool-response turns are not stored.

Context window strategy (Bug #19 fix):
  Raw turns kept verbatim  = RECENT_TURNS_WINDOW  (most recent turns)
  Extra turns fetched       = SUMMARY_LOOKAHEAD    (to detect overflow)

  If stored history > RECENT_TURNS_WINDOW, the overflow turns are
  compressed into a single lightweight summary sentinel prepended to
  the context — so the model stays aware of earlier topics without
  those bulky turns consuming the context window.

  Admin uses a tighter window because tool responses (event lists,
  booking tables) are much larger than plain customer messages and
  push the context window harder.
"""

from google.genai import types
from app.supabase_client import supabase_admin

# How many of the most recent messages to include verbatim.
# Admin sessions get a tighter window — tool responses (event lists,
# all-bookings tables) are much larger than customer chat messages and
# consume context budget far faster.
RECENT_TURNS_CUSTOMER = 16   # ~8 user/assistant pairs
RECENT_TURNS_ADMIN    = 10   # ~5 pairs  (tool responses are big)

# How many extra rows to fetch beyond the window to detect overflow.
# If we get more rows back than RECENT_TURNS_*, we know there's older
# history worth summarising rather than silently dropping.
SUMMARY_LOOKAHEAD = 6


def _table_for(agent: str) -> str:
    return "admin_chat_history" if agent == "admin" else "chat_history"


def _user_column_for(agent: str) -> str:
    return "admin_user_id" if agent == "admin" else "user_id"


def _window_for(agent: str) -> int:
    return RECENT_TURNS_ADMIN if agent == "admin" else RECENT_TURNS_CUSTOMER


def _build_summary_sentinel(overflow_rows: list[dict]) -> types.Content:
    """
    Compresses a list of older turns into a single compact summary
    turn that the model can use as lightweight earlier-context.

    Only user messages are summarised (assistant replies are usually
    verbose rewrites of the same info). The output is intentionally
    terse — it's a memory aid, not a full transcript.
    """
    topics = []
    for row in overflow_rows:
        if row.get("role") == "user" and row.get("message"):
            # Trim long messages to the first 80 chars so the sentinel
            # doesn't balloon — the model only needs to know the topic,
            # not the exact phrasing.
            snippet = row["message"].strip().replace("\n", " ")
            if len(snippet) > 80:
                snippet = snippet[:77] + "…"
            topics.append(snippet)

    if not topics:
        return None

    summary_text = (
        "[Earlier in this conversation the user discussed: "
        + " | ".join(topics)
        + ". Use this as background context only.]"
    )
    return types.Content(
        role="model",
        parts=[types.Part.from_text(text=summary_text)],
    )


def load_history(
    agent: str,
    user_id: str,
    session_id: str,
) -> list[types.Content]:
    """
    Loads recent turns for this session with context compression.

    Fetches RECENT_TURNS + SUMMARY_LOOKAHEAD rows.  If there are more
    rows than the window size, the overflow turns are compressed into a
    lightweight summary sentinel prepended to the recent verbatim turns
    — so the model is aware of earlier topics without those turns
    consuming the full context budget.

    Customer history uses chat_history.user_id.
    Admin history uses admin_chat_history.admin_user_id.
    """

    table = _table_for(agent)
    user_column = _user_column_for(agent)
    window = _window_for(agent)
    fetch_limit = window + SUMMARY_LOOKAHEAD

    result = (
        supabase_admin.table(table)
        .select("role, message")
        .eq(user_column, user_id)
        .eq("session_id", session_id)
        .order("created_at", desc=True)
        .limit(fetch_limit)
        .execute()
    )

    # Reverse so rows are chronological (oldest → newest)
    all_rows = list(reversed(result.data or []))

    # Split into overflow (older) and recent (verbatim) slices
    if len(all_rows) > window:
        overflow_rows = all_rows[: len(all_rows) - window]
        recent_rows   = all_rows[len(all_rows) - window :]
    else:
        overflow_rows = []
        recent_rows   = all_rows

    contents: list[types.Content] = []

    # Prepend a summary sentinel if there are compressed older turns
    if overflow_rows:
        sentinel = _build_summary_sentinel(overflow_rows)
        if sentinel:
            contents.append(sentinel)

    # Append the recent turns verbatim
    for row in recent_rows:
        if not row.get("message"):
            continue
        role = "model" if row["role"] == "assistant" else "user"
        contents.append(
            types.Content(
                role=role,
                parts=[types.Part.from_text(text=row["message"])],
            )
        )

    return contents


def save_turn(
    agent: str,
    user_id: str,
    session_id: str,
    user_message: str,
    assistant_reply: str,
) -> None:
    """
    Persists one completed turn.

    Customer history uses user_id.
    Admin history uses admin_user_id.
    """

    table = _table_for(agent)
    user_column = _user_column_for(agent)

    supabase_admin.table(table).insert(
        [
            {
                user_column: user_id,
                "session_id": session_id,
                "role": "user",
                "message": user_message,
            },
            {
                user_column: user_id,
                "session_id": session_id,
                "role": "assistant",
                "message": assistant_reply,
            },
        ]
    ).execute()