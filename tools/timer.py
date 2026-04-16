"""Countdown timer with audio alert."""
import asyncio
import re
import time
import threading
from typing import Dict, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

_active_timers: Dict[str, "TimerHandle"] = {}
_timer_counter = 0


class TimerHandle:
    __slots__ = ("name", "duration", "start_time", "cancelled")

    def __init__(self, name: str, duration: float):
        self.name = name
        self.duration = duration
        self.start_time = time.monotonic()
        self.cancelled = False


def _parse_duration(duration_str: str) -> float:
    """Parse a human duration string into seconds.

    Accepts: "5 minutes", "2m30s", "90 seconds", "1 hour", "1h30m", "30s", "5".
    """
    text = duration_str.strip().lower()

    m = re.match(
        r"(?:(\d+)\s*h(?:ours?)?)?[\s,]*(?:(\d+)\s*m(?:in(?:ute)?s?)?)?[\s,]*(?:(\d+)\s*s(?:ec(?:ond)?s?)?)?$",
        text,
    )
    if m and any(m.groups()):
        h = int(m.group(1) or 0)
        mins = int(m.group(2) or 0)
        s = int(m.group(3) or 0)
        return h * 3600 + mins * 60 + s

    m = re.match(r"(\d+(?:\.\d+)?)\s*(seconds?|secs?|s|minutes?|mins?|m|hours?|hrs?|h)?$", text)
    if m:
        val = float(m.group(1))
        unit = (m.group(2) or "m").rstrip("s")
        if unit in ("second", "sec", "s"):
            return val
        if unit in ("minute", "min", "m"):
            return val * 60
        if unit in ("hour", "hr", "h"):
            return val * 3600
        return val * 60

    raise ValueError(f"Cannot parse duration: {duration_str!r}")


def _play_alert() -> None:
    """Play a short alert sound using pygame.mixer if available."""
    try:
        import pygame
        if not pygame.mixer.get_init():
            pygame.mixer.init()
        alert_freq = 880
        sample_rate = 44100
        import numpy as np
        t = np.linspace(0, 0.5, int(sample_rate * 0.5), dtype=np.float32)
        wave = (np.sin(2 * np.pi * alert_freq * t) * 16000).astype(np.int16)
        stereo = np.column_stack((wave, wave))
        sound = pygame.sndarray.make_sound(stereo)
        sound.play()
        pygame.time.wait(600)
    except Exception as e:
        logger.warning(f"Timer alert sound failed (falling back to beep): {e}")
        try:
            import winsound
            winsound.Beep(880, 500)
        except Exception:
            print("\a")


def _timer_thread(handle: TimerHandle, label: str) -> None:
    """Background thread that sleeps then fires the alert."""
    remaining = handle.duration - (time.monotonic() - handle.start_time)
    if remaining > 0:
        time.sleep(remaining)
    if handle.cancelled:
        return
    logger.info(f"Timer '{handle.name}' finished ({label})")
    _play_alert()
    _active_timers.pop(handle.name, None)


async def set_timer(duration: str, label: str = "") -> dict:
    """Set a countdown timer.

    *duration*: human string like "5 minutes", "2m30s", "90 seconds".
    *label*: optional description (e.g. "pasta").
    """
    global _timer_counter

    try:
        seconds = _parse_duration(duration)
    except ValueError as e:
        from utils.error_handler import ToolExecutionError
        raise ToolExecutionError(str(e))

    _timer_counter += 1
    name = label or f"timer_{_timer_counter}"
    handle = TimerHandle(name, seconds)
    _active_timers[name] = handle

    thread = threading.Thread(target=_timer_thread, args=(handle, duration), daemon=True)
    thread.start()

    if seconds >= 3600:
        friendly = f"{seconds / 3600:.1f} hours"
    elif seconds >= 60:
        friendly = f"{seconds / 60:.0f} minutes"
    else:
        friendly = f"{seconds:.0f} seconds"

    logger.info(f"Timer set: {name} for {friendly} ({seconds}s)")
    return {
        "name": name,
        "duration_seconds": seconds,
        "duration_friendly": friendly,
        "summary": f"Timer set for {friendly}" + (f" ({label})" if label else ""),
    }


async def list_timers() -> dict:
    """List all active timers."""
    now = time.monotonic()
    timers = []
    for name, h in list(_active_timers.items()):
        elapsed = now - h.start_time
        remaining = max(0, h.duration - elapsed)
        timers.append({
            "name": name,
            "remaining_seconds": round(remaining, 1),
            "cancelled": h.cancelled,
        })
    return {"timers": timers, "count": len(timers)}


async def cancel_timer(name: str) -> dict:
    """Cancel an active timer by name."""
    handle = _active_timers.get(name)
    if handle:
        handle.cancelled = True
        _active_timers.pop(name, None)
        return {"cancelled": name, "summary": f"Timer '{name}' cancelled"}
    return {"cancelled": None, "summary": f"No active timer named '{name}'"}
