"""
Claude agent loop + tool calling. Used by the Telegram bot (`main.py`) and by the local CLI below.
"""

import json
import logging
from datetime import datetime

import pytz

import anthropic

from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from db import get_conversation_history, save_message
from tools.weather import WEATHER_TOOL_SCHEMA, get_weather
from tools.notes import NOTES_TOOL_SCHEMA, manage_notes
from tools.todos import TODOS_TOOL_SCHEMA, manage_todos
from tools.search import SEARCH_TOOL_SCHEMA, search_web
from tools.calendar import CALENDAR_TOOL_SCHEMA, manage_calendar

logger = logging.getLogger(__name__)

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

MODEL = ANTHROPIC_MODEL

# Map tool names to their Python implementations so we can dispatch by name
TOOLS = {
    "get_weather": get_weather,
    "manage_notes": manage_notes,
    "manage_todos": manage_todos,
    "search_web": search_web,
    "manage_calendar": manage_calendar,
}

# All tool schemas passed to Claude on every request
TOOL_SCHEMAS = [
    WEATHER_TOOL_SCHEMA,
    NOTES_TOOL_SCHEMA,
    TODOS_TOOL_SCHEMA,
    SEARCH_TOOL_SCHEMA,
    CALENDAR_TOOL_SCHEMA,
]


def _text_from_message_content(content) -> str:
    parts = []
    for block in content:
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            parts.append(block.text)
    return "".join(parts).strip()


def run_agent(user_message: str, telegram_user_id: int | None = None) -> str:
    """
    Run one turn of the agent loop for a single user message.

    Args:
        user_message: The text sent by the user.
        telegram_user_id: If provided, conversation history is loaded from Supabase
            before calling Claude, and both the user message and assistant reply are
            persisted after the response is ready.

    Returns:
        Claude's final text response.
    """
    # Load prior conversation history so Claude has context across messages.
    # Falls back to an empty list if Supabase is unavailable or user is unknown.
    if telegram_user_id is not None:
        history = get_conversation_history(telegram_user_id)
    else:
        history = []

    # Append the new user message after the history so Claude sees full context
    messages = history + [{"role": "user", "content": user_message}]

    toronto_tz = pytz.timezone("America/Toronto")
    today = datetime.now(toronto_tz).strftime("%A, %B %d, %Y")
    today_iso = datetime.now(toronto_tz).strftime("%Y-%m-%d")
    system_prompt = (
        f"Today is {today} (YYYY-MM-DD: {today_iso}). You are a helpful personal AI assistant. "
        "STRICT RULES YOU MUST FOLLOW:\n"
        "1. ALWAYS call manage_calendar tool for ANY scheduling request - never respond without calling it first\n"
        "2. ALWAYS call get_weather tool for ANY weather question\n"
        "3. ALWAYS call search_web tool for ANY current events or facts you don't know\n"
        "4. ALWAYS call manage_todos tool for ANY todo or reminder request\n"
        "5. ALWAYS call manage_notes tool for ANY note request\n"
        f"6. When calculating dates: today is {today}, tomorrow is the next day, use YYYY-MM-DD HH:MM format\n"
        "Never answer questions about weather, calendar, search, todos or notes from memory - always use the tools."
    )

    while True:
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
                system=system_prompt,
                tools=TOOL_SCHEMAS,
                messages=messages,
            )
        except anthropic.AuthenticationError:
            return (
                "Anthropic rejected the API key (401). Update ANTHROPIC_API_KEY in `.env` "
                "and avoid stale `export` values (this app loads `.env` with override)."
            )
        except anthropic.APIStatusError as e:
            return f"Anthropic API error ({getattr(e, 'status_code', '?')}): {e}"
        except anthropic.APIError as e:
            return f"Anthropic API error: {e}"

        if response.stop_reason == "end_turn":
            final_text = _text_from_message_content(response.content) or ""
            # Persist both sides of the exchange so history is available next turn
            if telegram_user_id is not None:
                save_message(telegram_user_id, "user", user_message)
                save_message(telegram_user_id, "assistant", final_text)
            return final_text

        if response.stop_reason in ("max_tokens", "stop_sequence"):
            partial = _text_from_message_content(response.content)
            if partial:
                # Still persist what we have so the conversation isn't lost
                if telegram_user_id is not None:
                    save_message(telegram_user_id, "user", user_message)
                    save_message(telegram_user_id, "assistant", partial)
                return partial
            return f"[Stopped: {response.stop_reason}; no text in this segment]"

        if response.stop_reason == "tool_use":
            # Step 3: Claude wants to call one or more tools
            # Add Claude's response (which contains the tool_use blocks) to messages
            messages.append({"role": "assistant", "content": response.content})

            # Collect results for all tool calls in this response
            tool_results = []

            for block in response.content:
                if block.type != "tool_use":
                    continue

                tool_name = block.name
                tool_input = block.input

                print(f"\n[Tool call] {tool_name}({json.dumps(tool_input, indent=2)})")

                # Step 4: Dispatch to the matching Python function.
                # For user-scoped tools (notes, todos) inject telegram_user_id so
                # Claude doesn't need to pass it explicitly in every call.
                tool_fn = TOOLS.get(tool_name)
                if tool_fn is None:
                    result = {"error": f"Unknown tool: {tool_name}"}
                else:
                    try:
                        kwargs = dict(tool_input)
                        if tool_name in ("manage_notes", "manage_todos", "manage_calendar"):
                            # Always inject the real user ID — never let Claude supply this value
                            kwargs["telegram_user_id"] = telegram_user_id
                        result = tool_fn(**kwargs)
                    except TypeError as e:
                        result = {"error": f"Invalid tool arguments: {e}"}
                    except Exception as e:
                        result = {"error": f"Tool failed: {e}"}

                print(f"[Tool result] {json.dumps(result, indent=2)}\n")

                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": json.dumps(result),
                })

            # Step 5: Send tool results back to Claude so it can formulate a reply
            messages.append({"role": "user", "content": tool_results})

            # Loop — Claude will now read the tool results and either respond or call more tools

        else:
            return (
                f"[Agent stopped unexpectedly: stop_reason={response.stop_reason}; "
                f"content={_text_from_message_content(response.content)!r}]"
            )


if __name__ == "__main__":
    print("Personal AI Agent — Phase 1 (Weather)")
    print("Type 'quit' or 'exit' to stop.\n")

    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nGoodbye!")
            break

        if not user_input:
            continue
        if user_input.lower() in {"quit", "exit"}:
            print("Goodbye!")
            break

        # telegram_user_id=None → no persistence in CLI mode
        response = run_agent(user_input)
        print(f"Agent: {response}\n")
