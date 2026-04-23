"""
Todos tool — CRUD operations on the `todos` Supabase table.
Each todo is scoped to a telegram_user_id so users only see their own data.

Expected columns: id, telegram_user_id, task, is_done, optional due_date, created_at
(Use BIGINT for telegram_user_id — Telegram user IDs can exceed 32-bit int.)
"""

import logging

from config import SUPABASE_TODOS_TABLE
from db import _get_client

logger = logging.getLogger(__name__)


def _todos_table(client):
    return client.table(SUPABASE_TODOS_TABLE)


def manage_todos(
    action: str,
    task: str = None,
    todo_id: str = None,
    due_date: str = None,
    telegram_user_id: int = None,
) -> dict:
    """
    Manage todos stored in Supabase.

    Actions: create, list, list_all, complete, delete
    """
    client = _get_client()
    if client is None:
        return {"error": "Database unavailable — Supabase credentials not configured."}

    if telegram_user_id is None:
        return {"error": "telegram_user_id is required to scope todos to a user."}

    try:
        if action == "create":
            if not task:
                return {"error": "'task' is required to create a todo."}
            payload = {"telegram_user_id": telegram_user_id, "task": task, "is_done": False}
            if due_date:
                payload["due_date"] = due_date
            t = _todos_table(client)
            # postgrest 2.28+: do not chain `.select()` after `.insert()` (not supported).
            # Insert uses return=representation by default; the row is in `res.data`.
            res = t.insert(payload).execute()
            rows = res.data or []
            if not rows:
                try:
                    alt = (
                        t.select("*")
                        .eq("telegram_user_id", telegram_user_id)
                        .eq("task", task)
                        .order("created_at", desc=True)
                        .limit(1)
                        .execute()
                    )
                    rows = alt.data or []
                except Exception as ve:
                    logger.warning("create fallback read failed: %s", ve)
            if not rows:
                return {
                    "error": (
                        f"Could not create or read a row in table `{SUPABASE_TODOS_TABLE}`. "
                        "Confirm: table name, and columns telegram_user_id (BIGINT), task (text), is_done (bool), "
                        "and optional due_date, created_at. Set SUPABASE_TODOS_TABLE if needed."
                    )
                }
            created = rows[0]
            logger.info("todo created id=%s table=%s", created.get("id"), SUPABASE_TODOS_TABLE)
            tid = created.get("id")
            return {
                "success": True,
                "todo_id": str(tid) if tid is not None else None,
                "task": created.get("task"),
            }

        elif action == "list":
            # Only incomplete todos
            rows = (
                _todos_table(client)
                .select("id, task, due_date, created_at")
                .eq("telegram_user_id", telegram_user_id)
                .eq("is_done", False)
                .order("created_at", desc=False)
                .execute()
            )
            return {"todos": rows.data or [], "count": len(rows.data or [])}

        elif action == "list_all":
            rows = (
                _todos_table(client)
                .select("id, task, due_date, is_done, created_at")
                .eq("telegram_user_id", telegram_user_id)
                .order("created_at", desc=False)
                .execute()
            )
            return {"todos": rows.data or [], "count": len(rows.data or [])}

        elif action == "complete":
            if not todo_id:
                return {"error": "'todo_id' is required to complete a todo."}
            rows = (
                _todos_table(client)
                .update({"is_done": True})
                .eq("id", todo_id)
                .eq("telegram_user_id", telegram_user_id)
                .execute()
            )
            if not rows.data:
                return {"error": f"Todo '{todo_id}' not found or does not belong to this user."}
            return {"success": True, "completed_todo_id": todo_id}

        elif action == "delete":
            if not todo_id:
                return {"error": "'todo_id' is required to delete a todo."}
            rows = (
                _todos_table(client)
                .delete()
                .eq("id", todo_id)
                .eq("telegram_user_id", telegram_user_id)
                .execute()
            )
            if not rows.data:
                return {"error": f"Todo '{todo_id}' not found or does not belong to this user."}
            return {"success": True, "deleted_todo_id": todo_id}

        else:
            return {
                "error": (
                    f"Unknown action '{action}'. "
                    "Valid actions: create, list, list_all, complete, delete."
                )
            }

    except Exception as e:
        logger.error("manage_todos(action=%s, user=%s) failed: %s", action, telegram_user_id, e)
        return {"error": f"Todos operation failed: {e}"}


TODOS_TOOL_SCHEMA = {
    "name": "manage_todos",
    "description": (
        "Create, list, complete, or delete personal to-do items stored in the database. "
        "Each todo has a task description and an optional due date. "
        "Todos are private to the current user. "
        "When the user asks to add, create, or remember a todo, you MUST call this tool with "
        "action=create and a non-empty 'task' string. Do not claim a todo was saved unless you actually invoked create and received success."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["create", "list", "list_all", "complete", "delete"],
                "description": (
                    "The operation to perform: "
                    "'create' — add a new todo; "
                    "'list' — list all incomplete todos; "
                    "'list_all' — list all todos including completed ones; "
                    "'complete' — mark a todo as done by todo_id; "
                    "'delete' — permanently remove a todo."
                ),
            },
            "task": {
                "type": "string",
                "description": "Description of the task. Required for 'create'.",
            },
            "todo_id": {
                "type": "string",
                "description": "UUID of the todo. Required for 'complete' and 'delete'.",
            },
            "due_date": {
                "type": "string",
                "description": (
                    "Optional due date for the todo in ISO 8601 format (e.g. '2025-12-31'). "
                    "Only used when creating a todo."
                ),
            },
        },
        "required": ["action"],
    },
}
