"""Weather lookup via wttr.in (free, no API key)."""
import asyncio
from typing import Optional

import requests

from utils.error_handler import ToolExecutionError
from utils.logger import get_logger

logger = get_logger(__name__)

WTTR_URL = "https://wttr.in/{location}?format=j1"
TIMEOUT = 8


async def get_weather(location: str = "") -> dict:
    """Fetch current weather for *location* (city name or empty for IP-based)."""
    url = WTTR_URL.format(location=requests.utils.quote(location or ""))
    loop = asyncio.get_event_loop()

    try:
        resp = await loop.run_in_executor(
            None, lambda: requests.get(url, timeout=TIMEOUT)
        )
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        raise ToolExecutionError(f"Weather lookup failed: {e}") from e

    cur = data.get("current_condition", [{}])[0]
    area = data.get("nearest_area", [{}])[0]
    city = area.get("areaName", [{}])[0].get("value", location or "your location")
    country = area.get("country", [{}])[0].get("value", "")

    desc = cur.get("weatherDesc", [{}])[0].get("value", "Unknown")
    temp_c = cur.get("temp_C", "?")
    temp_f = cur.get("temp_F", "?")
    feels_c = cur.get("FeelsLikeC", "?")
    humidity = cur.get("humidity", "?")
    wind_kph = cur.get("windspeedKmph", "?")
    wind_dir = cur.get("winddir16Point", "")

    summary = (
        f"{desc}, {temp_c}C ({temp_f}F), feels like {feels_c}C, "
        f"humidity {humidity}%, wind {wind_kph} km/h {wind_dir}"
    )
    logger.info(f"Weather for {city}: {summary}")

    return {
        "location": f"{city}, {country}".strip(", "),
        "description": desc,
        "temperature_c": temp_c,
        "temperature_f": temp_f,
        "feels_like_c": feels_c,
        "humidity": humidity,
        "wind_kph": wind_kph,
        "wind_direction": wind_dir,
        "summary": summary,
    }
