"""Replay recorded action cycles."""
import asyncio
import time
from typing import Dict, List

from automation.cycle_manager import CycleManager
from automation.recorder import RecordedAction
from utils.logger import get_logger

logger = get_logger(__name__)


class TriggerEngine:
    """Replays a saved cycle by sending input events with original timing."""

    def __init__(self, cycle_manager: CycleManager):
        self.cycles = cycle_manager

    async def play(self, name: str, speed: float = 1.0) -> Dict:
        cycle = self.cycles.load(name)
        raw_actions = cycle.get("actions", [])
        actions = [RecordedAction.from_dict(a) for a in raw_actions]
        return await self._replay(actions, speed)

    async def _replay(self, actions: List[RecordedAction], speed: float) -> Dict:
        try:
            import keyboard
            import mouse
        except ImportError as e:
            raise RuntimeError("playback requires `keyboard` and `mouse` packages") from e

        last_ts = 0.0
        played = 0
        for action in actions:
            delta = max(0.0, (action.timestamp - last_ts) / max(speed, 0.01))
            if delta > 0:
                await asyncio.sleep(delta)
            last_ts = action.timestamp

            if action.type == "key_down":
                keyboard.press(action.data["name"])
                played += 1
            elif action.type == "key_up":
                keyboard.release(action.data["name"])
                played += 1
            elif action.type == "click":
                btn = action.data.get("button", "left")
                evt = action.data.get("event_type", "click")
                if evt == "down":
                    mouse.press(btn)
                elif evt == "up":
                    mouse.release(btn)
                elif evt == "double":
                    mouse.double_click(btn)
                else:
                    mouse.click(btn)
                played += 1
            elif action.type == "move":
                x = action.data.get("x", 0)
                y = action.data.get("y", 0)
                mouse.move(x, y, absolute=True)
                played += 1
            elif action.type == "scroll":
                delta = action.data.get("delta", 0)
                mouse.wheel(delta)
                played += 1

        logger.info(f"Replayed {played}/{len(actions)} actions at {speed}x speed")
        return {"replayed": played, "total": len(actions), "speed": speed}
