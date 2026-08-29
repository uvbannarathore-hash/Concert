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
"""

from google.genai import types
from app.supabase_client import supabase_admin

MAX_HISTORY_MESSAGES = 20  # ~10 user/assistant turn pairs of context


def _table_for(agent: str) -> str:
    return "admin_chat_history" if agent == "admin" else "chat_history"


def _user_column_for(agent: str) -> str:
    return "admin_user_id" if agent == "admin" else "user_id"


def load_history(
    agent: str,
    user_id: str,
    session_id: str,
) -> list[types.Content]:
    """
    Loads the most recent turns for this session.

    Customer history uses chat_history.user_id.
    Admin history uses admin_chat_history.admin_user_id.
    """

    table = _table_for(agent)
    user_column = _user_column_for(agent)

    result = (
        supabase_admin.table(table)
        .select("role, message")
        .eq(user_column, user_id)
        .eq("session_id", session_id)
        .order("created_at", desc=True)
        .limit(MAX_HISTORY_MESSAGES)
        .execute()
    )

    rows = list(reversed(result.data or []))

    contents = []

    for row in rows:
        if not row.get("message"):
            continue

        role = "model" if row["role"] == "assistant" else "user"

        contents.append(
            types.Content(
                role=role,
                parts=[
                    types.Part.from_text(
                        text=row["message"]
                    )
                ],
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