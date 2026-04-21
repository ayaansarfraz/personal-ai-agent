"""
Supabase database helpers for conversation persistence.
All functions are keyed by telegram_user_id so each user has isolated history.
"""

import logging

from supabase import create_client, Client

from config import SUPABASE_URL, SUPABASE_KEY

logger = logging.getLogger(__name__)

# Module-level Supabase client (created once at import time)
_client: Client | None = None


def _get_client() -> Client | None:
    """Return the Supabase client, or None if credentials are missing."""
    global _client
    if _client is None:
        if not SUPABASE_URL or not SUPABASE_KEY:
            logger.error("SUPABASE_URL or SUPABASE_KEY is not set; database features disabled")
            return None
        _client = create_client(SUPABASE_URL, SUPABASE_KEY)
    return _client


def save_message(telegram_user_id: int, role: str, content: str) -> None:
    """
    Insert a single message into the conversations table.

    Args:
        telegram_user_id: Telegram user ID (used to namespace conversations).
        role: "user" or "assistant".
        content: The message text.
    """
    client = _get_client()
    if client is None:
        return

    try:
        client.table("conversations").insert({
            "telegram_user_id": telegram_user_id,
            "role": role,
            "content": content,
        }).execute()
    except Exception as e:
        logger.error("save_message failed for user %s: %s", telegram_user_id, e)


def get_conversation_history(telegram_user_id: int, limit: int = 20) -> list[dict]:
    """
    Fetch the last `limit` messages for a user, ordered oldest-first.

    Returns a list of {"role": ..., "content": ...} dicts ready to pass
    directly as the `messages` parameter to the Claude API.
    """
    client = _get_client()
    if client is None:
        return []

    try:
        response = (
            client.table("conversations")
            .select("role, content, created_at")
            .eq("telegram_user_id", telegram_user_id)
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )
        # Rows come back newest-first; reverse so they're chronological for Claude
        rows = list(reversed(response.data or []))
        return [{"role": row["role"], "content": row["content"]} for row in rows]
    except Exception as e:
        logger.error("get_conversation_history failed for user %s: %s", telegram_user_id, e)
        return []


def clear_conversation(telegram_user_id: int) -> None:
    """
    Delete all conversation messages for a user.

    Useful for a /clear or /reset Telegram command.
    """
    client = _get_client()
    if client is None:
        return

    try:
        client.table("conversations").delete().eq("telegram_user_id", telegram_user_id).execute()
    except Exception as e:
        logger.error("clear_conversation failed for user %s: %s", telegram_user_id, e)
