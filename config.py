import os
from pathlib import Path

from dotenv import load_dotenv

# Load repo-root `.env` even if cwd is elsewhere; `override=True` so shell exports
# (e.g. old ANTHROPIC_API_KEY in ~/.zshrc) cannot hide the keys you edited in `.env`.
load_dotenv(Path(__file__).resolve().parent / ".env", override=True)


def _str_env(name: str) -> str | None:
    raw = os.getenv(name)
    if raw is None:
        return None
    stripped = raw.strip().strip('"').strip("'")
    return stripped or None


ANTHROPIC_API_KEY = _str_env("ANTHROPIC_API_KEY")
# Telegram bot (used by main.py). Optional at import time — main.py exits if unset when you run the bot.
TELEGRAM_BOT_TOKEN = _str_env("TELEGRAM_BOT_TOKEN")
# Optional: agent runs without it; get_weather returns an error dict until configured.
OPENWEATHERMAP_API_KEY = _str_env("OPENWEATHERMAP_API_KEY")
# Optional override; use a dated ID if the short alias is unavailable for your account.
ANTHROPIC_MODEL = _str_env("ANTHROPIC_MODEL") or "claude-sonnet-4-5-20250929"
# Supabase — used by db.py and tools (notes, todos). Optional: bot runs without them.
# For Telegram, use the project service_role key (Settings → API) if RLS blocks inserts;
# the anon key often cannot INSERT into user-scoped tables without matching policies.
SUPABASE_URL = _str_env("SUPABASE_URL")
SUPABASE_KEY = _str_env("SUPABASE_KEY")
# Optional: if your table is not named "todos" in the public schema
SUPABASE_TODOS_TABLE = _str_env("SUPABASE_TODOS_TABLE") or "todos"
# Tavily Search API — used by tools/search.py. Required for web search.
TAVILY_API_KEY = _str_env("TAVILY_API_KEY")

if not ANTHROPIC_API_KEY:
    raise EnvironmentError("Missing required environment variable: ANTHROPIC_API_KEY")
if not TAVILY_API_KEY:
    raise EnvironmentError("Missing required environment variable: TAVILY_API_KEY")
