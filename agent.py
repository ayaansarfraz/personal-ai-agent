import json

import anthropic

from config import ANTHROPIC_API_KEY, ANTHROPIC_MODEL
from tools.weather import WEATHER_TOOL_SCHEMA, get_weather

client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

MODEL = ANTHROPIC_MODEL

# Map tool names to their Python implementations so we can dispatch by name
TOOLS = {
    "get_weather": get_weather,
}

# All tool schemas passed to Claude on every request
TOOL_SCHEMAS = [WEATHER_TOOL_SCHEMA]


def _text_from_message_content(content) -> str:
    parts = []
    for block in content:
        if getattr(block, "type", None) == "text" and getattr(block, "text", None):
            parts.append(block.text)
    return "".join(parts).strip()


def run_agent(user_message: str) -> str:
    """
    Run one turn of the agent loop for a single user message.
    Returns Claude's final text response.
    """
    messages = [{"role": "user", "content": user_message}]

    while True:
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=1024,
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
            return _text_from_message_content(response.content) or ""

        if response.stop_reason in ("max_tokens", "stop_sequence"):
            partial = _text_from_message_content(response.content)
            if partial:
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

                # Step 4: Dispatch to the matching Python function
                tool_fn = TOOLS.get(tool_name)
                if tool_fn is None:
                    result = {"error": f"Unknown tool: {tool_name}"}
                else:
                    try:
                        result = tool_fn(**tool_input)
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

        response = run_agent(user_input)
        print(f"Agent: {response}\n")
