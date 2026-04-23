"""
Notes tool — CRUD operations on the `notes` Supabase table.
Each note is scoped to a telegram_user_id so users only see their own data.
"""

import logging

from db import _get_client

logger = logging.getLogger(__name__)


def manage_notes(
    action: str,
    title: str = None,
    content: str = None,
    note_id: str = None,
    telegram_user_id: int = None,
) -> dict:
    """
    Manage notes stored in Supabase.

    Actions: create, list, read, update, delete
    """
    client = _get_client()
    if client is None:
        return {"error": "Database unavailable — Supabase credentials not configured."}

    if telegram_user_id is None:
        return {"error": "telegram_user_id is required to scope notes to a user."}

    try:
        if action == "create":
            if not title or not content:
                return {"error": "Both 'title' and 'content' are required to create a note."}
            row = (
                client.table("notes")
                .insert({"telegram_user_id": telegram_user_id, "title": title, "content": content})
                .execute()
            )
            created = row.data[0] if row.data else {}
            return {"success": True, "note_id": created.get("id"), "title": created.get("title")}

        elif action == "list":
            rows = (
                client.table("notes")
                .select("id, title, content, created_at")
                .eq("telegram_user_id", telegram_user_id)
                .order("created_at", desc=True)
                .execute()
            )
            notes = [
                {
                    "id": r["id"],
                    "title": r["title"],
                    "preview": (r.get("content") or "")[:50],
                    "created_at": r["created_at"],
                }
                for r in (rows.data or [])
            ]
            return {"notes": notes, "count": len(notes)}

        elif action == "read":
            if not note_id:
                return {"error": "'note_id' is required to read a note."}
            rows = (
                client.table("notes")
                .select("id, title, content, created_at")
                .eq("id", note_id)
                .eq("telegram_user_id", telegram_user_id)
                .execute()
            )
            if not rows.data:
                return {"error": f"Note '{note_id}' not found."}
            return rows.data[0]

        elif action == "update":
            if not note_id:
                return {"error": "'note_id' is required to update a note."}
            if content is None:
                return {"error": "'content' is required to update a note."}
            rows = (
                client.table("notes")
                .update({"content": content})
                .eq("id", note_id)
                .eq("telegram_user_id", telegram_user_id)
                .execute()
            )
            if not rows.data:
                return {"error": f"Note '{note_id}' not found or does not belong to this user."}
            return {"success": True, "note_id": note_id}

        elif action == "delete":
            if not note_id:
                return {"error": "'note_id' is required to delete a note."}
            rows = (
                client.table("notes")
                .delete()
                .eq("id", note_id)
                .eq("telegram_user_id", telegram_user_id)
                .execute()
            )
            if not rows.data:
                return {"error": f"Note '{note_id}' not found or does not belong to this user."}
            return {"success": True, "deleted_note_id": note_id}

        else:
            return {"error": f"Unknown action '{action}'. Valid actions: create, list, read, update, delete."}

    except Exception as e:
        logger.error("manage_notes(action=%s, user=%s) failed: %s", action, telegram_user_id, e)
        return {"error": f"Notes operation failed: {e}"}


NOTES_TOOL_SCHEMA = {
    "name": "manage_notes",
    "description": (
        "Create, list, read, update, or delete personal notes stored in the database. "
        "Each note has a title and content. Notes are private to the current user."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "list", "read", "update", "delete"],
                "description": (
                    "The operation to perform: "
                    "'create' — add a new note; "
                    "'list' — list all notes (id, title, preview, created_at); "
                    "'read' — get full content of one note by note_id; "
                    "'update' — replace content of an existing note; "
                    "'delete' — permanently remove a note."
                ),
            },
            "title": {
                "type": "string",
                "description": "Note title. Required for 'create'.",
            },
            "content": {
                "type": "string",
                "description": "Note body text. Required for 'create' and 'update'.",
            },
            "note_id": {
                "type": "string",
                "description": "UUID of the note. Required for 'read', 'update', and 'delete'.",
            },
        },
        "required": ["action"],
    },
}
