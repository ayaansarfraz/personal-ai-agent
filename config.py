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
# Optional: agent runs without it; get_weather returns an error dict until configured.
OPENWEATHERMAP_API_KEY = _str_env("OPENWEATHERMAP_API_KEY")
# Optional override; use a dated ID if the short alias is unavailable for your account.
ANTHROPIC_MODEL = _str_env("ANTHROPIC_MODEL") or "claude-sonnet-4-5-20250929"

if not ANTHROPIC_API_KEY:
    raise EnvironmentError("Missing required environment variable: ANTHROPIC_API_KEY")
