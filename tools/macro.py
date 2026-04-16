"""Macro recording and playback tool interface."""
import asyncio
import threading
from typing import Optional

from automation.cycle_manager import CycleManager
from automation.recorder import ActionRecorder
from automation.trigger_engine import TriggerEngine
from utils.error_handler import ToolExecutionError
from utils.logger import get_logger

logger = get_logger(__name__)

_recorder = ActionRecorder()
_cycles = CycleManager()
_trigger = TriggerEngine(_cycles)


async def start_recording() -> dict:
    """Start recording mouse and keyboard actions."""
    if _recorder.recording:
        return {"status": "already_recording", "summary": "Already recording a macro."}

    _recorder.start()
    return {"status": "recording", "summary": "Macro recording started. Say 'stop recording' when done."}


async def stop_recording(name: str = "") -> dict:
    """Stop recording and save the macro."""
    if not _recorder.recording:
        return {"status": "not_recording", "summary": "No recording in progress."}

    actions = _recorder.stop()
    if not actions:
        return {"status": "empty", "summary": "Recording stopped but no actions were captured."}

    macro_name = name or f"macro_{len(_cycles.list()) + 1}"
    action_dicts = _recorder.to_list()
    path = _cycles.save(macro_name, action_dicts)
    duration = _recorder.get_duration()

    logger.info(f"Macro '{macro_name}' saved: {len(actions)} actions, {duration:.1f}s")
    return {
        "name": macro_name,
        "actions": len(actions),
        "duration_seconds": round(duration, 1),
        "path": str(path),
        "summary": f"Macro '{macro_name}' saved ({len(actions)} actions, {duration:.1f}s)",
    }


async def play_macro(name: str, speed: float = 1.0) -> dict:
    """Replay a saved macro by name."""
    available = _cycles.list()
    if name not in available:
        raise ToolExecutionError(
            f"Macro '{name}' not found. Available: {', '.join(available) or 'none'}"
        )

    result = await _trigger.play(name, speed=speed)
    return {
        "name": name,
        "replayed": result["replayed"],
        "speed": speed,
        "summary": f"Replayed macro '{name}' ({result['replayed']} actions at {speed}x)",
    }


async def list_macros() -> dict:
    """List all saved macros."""
    names = _cycles.list()
    macros = []
    for n in names:
        try:
            data = _cycles.load(n)
            count = len(data.get("actions", []))
            macros.append({"name": n, "actions": count})
        except Exception:
            macros.append({"name": n, "actions": "?"})

    summary = (
        f"{len(macros)} macros: " + ", ".join(m["name"] for m in macros)
        if macros else "No macros saved yet"
    )
    return {"macros": macros, "count": len(macros), "summary": summary}


async def delete_macro(name: str) -> dict:
    """Delete a saved macro."""
    if _cycles.delete(name):
        return {"deleted": name, "summary": f"Macro '{name}' deleted"}
    raise ToolExecutionError(f"Macro '{name}' not found")
