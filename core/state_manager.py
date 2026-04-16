"""Real-time system state tracker."""
import sys
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

import psutil

try:
    import pygetwindow as gw
except ImportError:  # pygetwindow is optional on non-Windows builds
    gw = None


class SystemMode(Enum):
    NORMAL = "normal"
    AI_MODE = "ai_mode"
    AUTOMATION = "automation"
    LISTENING = "listening"
    SILENT = "silent"
    SPEECH = "speech"


@dataclass
class SystemState:
    """
    Real-time system state tracker.
    Prevents redundant actions and enables context-aware responses.
    """

    # Application state
    active_app: Optional[str] = None
    open_windows: List[str] = field(default_factory=list)
    foreground_window: Optional[str] = None

    # Media state
    media_playing: bool = False
    media_source: Optional[str] = None
    media_title: Optional[str] = None
    volume_level: int = 50

    # Browser state
    active_browser: Optional[str] = None
    open_tabs: List[Dict[str, str]] = field(default_factory=list)
    current_url: Optional[str] = None

    # System state
    mode: SystemMode = SystemMode.NORMAL
    last_command: Optional[str] = None
    last_command_time: Optional[float] = None

    # Automation state
    recording: bool = False
    recorded_actions: List[Dict[str, Any]] = field(default_factory=list)

    def update_active_app(self) -> None:
        """Poll the OS for the foreground window and list of open windows."""
        if gw is None:
            return

        try:
            active = gw.getActiveWindow()
        except Exception:
            active = None

        if active is not None:
            title = getattr(active, "title", None) or str(active)
            self.foreground_window = title or None
            self.active_app = title or None
        else:
            self.foreground_window = None

        try:
            titles = [t for t in gw.getAllTitles() if t]
            self.open_windows = titles
        except Exception:
            pass

    def get_open_applications(self) -> List[str]:
        """Get list of currently running applications."""
        apps = []
        for proc in psutil.process_iter(["name"]):
            try:
                apps.append(proc.info["name"])
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass
        return list(set(apps))

    def should_skip_action(self, action: dict) -> bool:
        """Determine if an action is redundant based on current state."""
        tool = action.get("tool")
        params = action.get("params", {}) or {}

        if tool == "open_application":
            app_name = params.get("app_name", "").lower()
            return app_name in [a.lower() for a in self.open_windows]

        if tool == "play_media" or (tool == "control_media" and params.get("action") == "play"):
            return self.media_playing

        if tool == "pause_media" or (tool == "control_media" and params.get("action") == "pause"):
            return not self.media_playing

        return False

    def record_command(self, command: str) -> None:
        self.last_command = command
        self.last_command_time = time.time()

    def to_context_string(self) -> str:
        """Convert state to concise string for LLM context."""
        parts = []
        if self.active_app:
            parts.append(f"Active app: {self.active_app}")
        if self.media_playing:
            parts.append(
                f"Playing: {self.media_title or 'media'} on {self.media_source or 'unknown'}"
            )
        if self.mode != SystemMode.NORMAL:
            parts.append(f"Mode: {self.mode.value}")
        return " | ".join(parts) if parts else "Idle"
