import httpx
from config import OPENWEATHERMAP_API_KEY

BASE_URL = "https://api.openweathermap.org/data/2.5/weather"


def get_weather(city: str, units: str = "metric") -> dict:
    """Call OpenWeatherMap API and return a clean weather summary."""
    if not OPENWEATHERMAP_API_KEY:
        return {"error": "OpenWeatherMap API key not configured. Set OPENWEATHERMAP_API_KEY in .env."}

    params = {
        "q": city,
        "appid": OPENWEATHERMAP_API_KEY,
        "units": units,
    }

    try:
        response = httpx.get(BASE_URL, params=params, timeout=10)
    except httpx.RequestError as e:
        return {"error": f"Network error while fetching weather: {e}"}

    if response.status_code == 404:
        return {"error": f"City '{city}' not found. Check the spelling and try again."}
    if response.status_code == 401:
        return {"error": "Invalid OpenWeatherMap API key."}
    if response.status_code != 200:
        return {"error": f"OpenWeatherMap API error (status {response.status_code}): {response.text}"}

    data = response.json()

    unit_labels = {"metric": "°C", "imperial": "°F", "standard": "K"}
    unit_label = unit_labels.get(units, "")
    main = data.get("main") or {}
    weather = (data.get("weather") or [{}])[0]
    wind = data.get("wind") or {}
    speed = wind.get("speed", 0)
    wind_unit = "m/s" if units == "metric" else "mph"

    return {
        "city": data["name"],
        "temperature": f"{main.get('temp', '')}{unit_label}",
        "feels_like": f"{main.get('feels_like', '')}{unit_label}",
        "humidity": f"{main.get('humidity', '')}%",
        "description": (weather.get("description") or "").capitalize(),
        "wind_speed": f"{speed} {wind_unit}",
        "units": units,
    }


# Tool schema for Claude — follows Anthropic's tool use format
WEATHER_TOOL_SCHEMA = {
    "name": "get_weather",
    "description": (
        "Get the current weather for a given city. "
        "Returns temperature, feels-like temperature, humidity, "
        "weather description, and wind speed."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "city": {
                "type": "string",
                "description": "The name of the city to get weather for (e.g. 'London', 'New York').",
            },
            "units": {
                "type": "string",
                "enum": ["metric", "imperial", "standard"],
                "description": (
                    "Unit system for temperature. "
                    "'metric' = Celsius (default), 'imperial' = Fahrenheit, 'standard' = Kelvin."
                ),
            },
        },
        "required": ["city"],
    },
}
