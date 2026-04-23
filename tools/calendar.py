"""
Google Calendar tool — list, create, delete events and find free time slots.

OAuth2 credentials are loaded from `credentials.json` in the project root.
After first login the token is cached in `token.json` so re-authentication
is not required on subsequent calls.
"""

import logging
from datetime import datetime, timedelta
from pathlib import Path

import pytz

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)

# Project root — two levels up from tools/calendar.py
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CREDENTIALS_FILE = _PROJECT_ROOT / "credentials.json"
_TOKEN_FILE = _PROJECT_ROOT / "token.json"

SCOPES = ["https://www.googleapis.com/auth/calendar"]
_TORONTO_TZ = pytz.timezone("America/Toronto")


def _get_calendar_service():
    """Authenticate and return a Google Calendar API service object."""
    creds = None

    # Load cached token if it exists
    if _TOKEN_FILE.exists():
        creds = Credentials.from_authorized_user_file(str(_TOKEN_FILE), SCOPES)

    # Refresh or re-run the OAuth flow if the token is missing or expired
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except Exception as e:
                # Refresh token revoked or expired — fall through to full OAuth flow
                logger.warning("Token refresh failed (%s); re-running OAuth flow.", e)
                creds = None

        if not creds:
            if not _CREDENTIALS_FILE.exists():
                raise FileNotFoundError(
                    f"credentials.json not found at {_CREDENTIALS_FILE}. "
                    "Download it from Google Cloud Console → APIs & Services → Credentials "
                    "(OAuth 2.0 Client IDs → Download JSON)."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(_CREDENTIALS_FILE), SCOPES)
            creds = flow.run_local_server(port=0)

        # Persist the token so the next call skips the browser flow
        _TOKEN_FILE.write_text(creds.to_json())

    return build("calendar", "v3", credentials=creds)


def _parse_event(event: dict) -> dict:
    """Extract clean, readable fields from a raw Google Calendar event dict."""
    start = event.get("start", {})
    end = event.get("end", {})
    result = {
        "event_id": event.get("id"),
        "summary": event.get("summary", "(no title)"),
        "start": start.get("dateTime") or start.get("date"),
        "end": end.get("dateTime") or end.get("date"),
    }
    if location := event.get("location"):
        result["location"] = location
    return result


def manage_calendar(
    action: str,
    summary: str = None,
    start_time: str = None,
    end_time: str = None,
    date: str = None,
    event_id: str = None,
    telegram_user_id: int = None,  # accepted for interface consistency; unused by OAuth flow
) -> dict:
    """
    Manage Google Calendar events.

    Actions: list_events, create_event, delete_event, find_free_time
    """
    try:
        service = _get_calendar_service()
    except FileNotFoundError as e:
        return {"error": str(e)}
    except Exception as e:
        logger.error("Calendar auth failed: %s", e)
        return {"error": f"Google Calendar authentication failed: {e}"}

    try:
        if action == "list_events":
            return _list_events(service, date)

        elif action == "create_event":
            if not summary:
                return {"error": "'summary' is required to create an event."}
            if not start_time or not end_time:
                return {"error": "'start_time' and 'end_time' are required to create an event."}
            return _create_event(service, summary, start_time, end_time)

        elif action == "delete_event":
            if not event_id:
                return {"error": "'event_id' is required to delete an event."}
            return _delete_event(service, event_id)

        elif action == "find_free_time":
            return _find_free_time(service, date)

        else:
            return {
                "error": (
                    f"Unknown action '{action}'. "
                    "Valid actions: list_events, create_event, delete_event, find_free_time."
                )
            }

    except HttpError as e:
        logger.error("Google Calendar API error (action=%s): %s", action, e)
        return {"error": f"Google Calendar API error: {e}"}
    except Exception as e:
        logger.error("manage_calendar(action=%s) failed: %s", action, e)
        return {"error": f"Calendar operation failed: {e}"}


def _list_events(service, date: str = None) -> dict:
    """List events for a specific date, or the next 7 days if no date is given."""
    if date:
        try:
            day_naive = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return {"error": f"Invalid date format '{date}'. Use YYYY-MM-DD."}
        time_min = _TORONTO_TZ.localize(day_naive.replace(hour=0, minute=0, second=0, microsecond=0))
        time_max = _TORONTO_TZ.localize(day_naive.replace(hour=23, minute=59, second=59, microsecond=0))
    else:
        time_min = datetime.now(_TORONTO_TZ)
        time_max = time_min + timedelta(days=7)

    result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=time_min.isoformat(),
            timeMax=time_max.isoformat(),
            singleEvents=True,
            orderBy="startTime",
            maxResults=50,
        )
        .execute()
    )

    events = [_parse_event(e) for e in result.get("items", [])]
    label = date if date else "next 7 days"
    return {"events": events, "count": len(events), "period": label}


def _normalize_datetime(dt_str: str) -> str:
    """
    Coerce common Claude-produced datetime strings to ISO 8601 for the Google Calendar API.

    Handles:
      "2026-04-24 10:00"     → "2026-04-24T10:00:00"
      "2026-04-24T10:00"     → "2026-04-24T10:00:00"
      "2026-04-24T10:00:00"  → unchanged
    """
    # Normalise space separator to T
    dt_str = dt_str.strip().replace(" ", "T", 1)
    # Append :00 seconds if only HH:MM is present (16 chars = "YYYY-MM-DDTHH:MM")
    if len(dt_str) == 16:
        dt_str += ":00"
    return dt_str


def _create_event(service, summary: str, start_time: str, end_time: str) -> dict:
    """Create a new calendar event. Accepts ISO 8601 or 'YYYY-MM-DD HH:MM' strings."""
    start_time = _normalize_datetime(start_time)
    end_time = _normalize_datetime(end_time)
    body = {
        "summary": summary,
        "start": {"dateTime": start_time, "timeZone": "America/Toronto"},
        "end": {"dateTime": end_time, "timeZone": "America/Toronto"},
    }
    event = service.events().insert(calendarId="primary", body=body).execute()
    return {
        "success": True,
        "event": _parse_event(event),
        "html_link": event.get("htmlLink"),
    }


def _delete_event(service, event_id: str) -> dict:
    """Delete a calendar event by its Google Calendar event ID."""
    # Confirm the event exists before attempting deletion
    try:
        service.events().get(calendarId="primary", eventId=event_id).execute()
    except HttpError as e:
        if e.resp.status == 404:
            return {"error": f"Event '{event_id}' not found."}
        raise

    service.events().delete(calendarId="primary", eventId=event_id).execute()
    return {"success": True, "deleted_event_id": event_id}


def _find_free_time(service, date: str = None) -> dict:
    """Find available 1-hour slots between 09:00 and 18:00 America/Toronto on the given date."""
    if date:
        try:
            day_naive = datetime.strptime(date, "%Y-%m-%d")
        except ValueError:
            return {"error": f"Invalid date format '{date}'. Use YYYY-MM-DD."}
    else:
        day_naive = datetime.now(_TORONTO_TZ).replace(tzinfo=None)

    # Working window: 9am – 6pm America/Toronto (localize handles DST automatically)
    window_start = _TORONTO_TZ.localize(day_naive.replace(hour=9, minute=0, second=0, microsecond=0))
    window_end = _TORONTO_TZ.localize(day_naive.replace(hour=18, minute=0, second=0, microsecond=0))

    freebusy = (
        service.freebusy()
        .query(
            body={
                "timeMin": window_start.isoformat(),
                "timeMax": window_end.isoformat(),
                "items": [{"id": "primary"}],
            }
        )
        .execute()
    )
    busy_periods = freebusy.get("calendars", {}).get("primary", {}).get("busy", [])

    # Walk the working window in 1-hour chunks and collect unblocked slots
    free_slots = []
    cursor = window_start
    slot_duration = timedelta(hours=1)

    while cursor + slot_duration <= window_end:
        slot_end = cursor + slot_duration
        # A slot is busy if any busy period overlaps [cursor, slot_end)
        overlaps = any(
            datetime.fromisoformat(b["start"]) < slot_end
            and datetime.fromisoformat(b["end"]) > cursor
            for b in busy_periods
        )
        if not overlaps:
            free_slots.append({"start": cursor.isoformat(), "end": slot_end.isoformat()})
        cursor = slot_end

    label = date if date else day_naive.strftime("%Y-%m-%d")
    return {
        "date": label,
        "free_slots": free_slots,
        "count": len(free_slots),
        "note": "Slots are 1-hour blocks between 09:00–18:00 America/Toronto.",
    }


CALENDAR_TOOL_SCHEMA = {
    "name": "manage_calendar",
    "description": (
        "Manage Google Calendar events. "
        "List upcoming events, create new events, delete events by ID, or find free 1-hour slots. "
        "Use this tool whenever the user asks about their schedule, wants to add a meeting, "
        "cancel an event, or check availability on a specific day."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "enum": ["list_events", "create_event", "delete_event", "find_free_time"],
                "description": (
                    "The calendar operation to perform: "
                    "'list_events' — list events for a date or the next 7 days if no date given; "
                    "'create_event' — add a new event (requires summary, start_time, end_time); "
                    "'delete_event' — remove an event by its event_id; "
                    "'find_free_time' — find available 1-hour slots on a date (09:00–18:00 America/Toronto)."
                ),
            },
            "summary": {
                "type": "string",
                "description": "Event title. Required for 'create_event'.",
            },
            "start_time": {
                "type": "string",
                "description": (
                    "Event start time in YYYY-MM-DD HH:MM format (e.g. '2026-04-24 14:00'). "
                    "ALWAYS resolve relative terms like 'tomorrow', 'next Monday', or 'this Friday' "
                    "to an explicit date using today's date before calling this tool. "
                    "Required for 'create_event'."
                ),
            },
            "end_time": {
                "type": "string",
                "description": (
                    "Event end time in YYYY-MM-DD HH:MM format (e.g. '2026-04-24 15:00'). "
                    "Must use the same explicit date as start_time. "
                    "Required for 'create_event'."
                ),
            },
            "date": {
                "type": "string",
                "description": (
                    "Date in YYYY-MM-DD format (e.g. '2026-04-24'). "
                    "ALWAYS resolve relative terms like 'tomorrow' or 'next Monday' to an explicit "
                    "date using today's date before calling this tool. "
                    "Used by 'list_events' (defaults to next 7 days if omitted) "
                    "and 'find_free_time' (defaults to today if omitted)."
                ),
            },
            "event_id": {
                "type": "string",
                "description": "Google Calendar event ID. Required for 'delete_event'.",
            },
        },
        "required": ["action"],
    },
}
