"""Local reminder + calendar event store."""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

from utils.error_handler import ToolExecutionError
from utils.logger import get_logger

logger = get_logger(__name__)

REMINDERS_FILE = Path(
    os.environ.get("AURIX_REMINDERS_PATH", Path.home() / ".aurix" / "reminders.json")
)


def _load() -> list:
    if not REMINDERS_FILE.exists():
        return []
    try:
        with open(REMINDERS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save(reminders: list) -> None:
    REMINDERS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(REMINDERS_FILE, "w", encoding="utf-8") as f:
        json.dump(reminders, f, indent=2)


async def create_reminder(message: str, time: str) -> dict:
    """Persist a reminder to a local JSON store."""
    if not message:
        raise ToolExecutionError("Reminder message is empty")

    reminder = {
        "message": message,
        "time": time,
        "created": datetime.now().isoformat(),
    }
    reminders = _load()
    reminders.append(reminder)
    _save(reminders)
    logger.info(f"Created reminder: {message} @ {time}")
    return reminder


async def list_reminders(limit: Optional[int] = None) -> dict:
    reminders = _load()
    if limit:
        reminders = reminders[:limit]
    return {"reminders": reminders, "count": len(reminders)}


async def clear_reminders() -> dict:
    _save([])
    return {"cleared": True}
