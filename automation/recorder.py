"""Record user mouse + keyboard actions for later playback."""
import json
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional

from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class RecordedAction:
    type: str       # "key_down", "key_up", "click", "move", "scroll"
    data: Dict[str, Any]
    timestamp: float

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "RecordedAction":
        return cls(type=d["type"], data=d["data"], timestamp=d["timestamp"])


class ActionRecorder:
    """Captures keyboard and mouse input events into a timed sequence."""

    def __init__(self):
        self.actions: List[RecordedAction] = []
        self.recording: bool = False
        self._start_time: float = 0.0
        self._keyboard_hook: Any = None
        self._mouse_hook: Any = None

    def start(self) -> None:
        if self.recording:
            return
        try:
            import keyboard
            import mouse
        except ImportError:
            logger.error("recorder requires `keyboard` and `mouse` packages")
            raise

        self.actions.clear()
        self._start_time = time.time()
        self.recording = True

        def on_key(event):
            etype = "key_down" if event.event_type == "down" else "key_up"
            self.actions.append(RecordedAction(
                type=etype,
                data={"name": event.name, "scan_code": event.scan_code},
                timestamp=time.time() - self._start_time,
            ))

        def on_mouse(event):
            import mouse as _m
            if isinstance(event, _m.ButtonEvent):
                self.actions.append(RecordedAction(
                    type="click",
                    data={
                        "button": event.button,
                        "event_type": event.event_type,
                        "x": getattr(event, "x", None),
                        "y": getattr(event, "y", None),
                    },
                    timestamp=time.time() - self._start_time,
                ))
            elif isinstance(event, _m.MoveEvent):
                self.actions.append(RecordedAction(
                    type="move",
                    data={"x": event.x, "y": event.y},
                    timestamp=time.time() - self._start_time,
                ))
            elif isinstance(event, _m.WheelEvent):
                self.actions.append(RecordedAction(
                    type="scroll",
                    data={"delta": event.delta},
                    timestamp=time.time() - self._start_time,
                ))

        self._keyboard_hook = keyboard.hook(on_key)
        self._mouse_hook = mouse.hook(on_mouse)
        logger.info("Recording started")

    def stop(self) -> List[RecordedAction]:
        if not self.recording:
            return self.actions
        import keyboard
        import mouse

        if self._keyboard_hook is not None:
            keyboard.unhook(self._keyboard_hook)
        if self._mouse_hook is not None:
            mouse.unhook(self._mouse_hook)

        self.recording = False
        self._compact_moves()
        logger.info(f"Recording stopped -- {len(self.actions)} actions captured")
        return self.actions

    def _compact_moves(self) -> None:
        """Drop redundant consecutive mouse moves, keep only the last per 50ms window."""
        if not self.actions:
            return
        compacted: List[RecordedAction] = []
        for a in self.actions:
            if a.type == "move" and compacted and compacted[-1].type == "move":
                if a.timestamp - compacted[-1].timestamp < 0.05:
                    compacted[-1] = a
                    continue
            compacted.append(a)
        self.actions = compacted

    def get_duration(self) -> float:
        if not self.actions:
            return 0.0
        return self.actions[-1].timestamp

    def to_list(self) -> List[dict]:
        return [a.to_dict() for a in self.actions]

    @staticmethod
    def from_list(data: List[dict]) -> List["RecordedAction"]:
        return [RecordedAction.from_dict(d) for d in data]
