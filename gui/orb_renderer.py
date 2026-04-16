"""Legacy orb renderer — disabled. The Electron sphere + HUD panel replace it.

This stub is kept so existing imports don't break. All methods are no-ops.
"""
from utils.logger import get_logger

logger = get_logger(__name__)


class OrbGUI:
    """No-op stub. Visual output is now handled by the Electron sphere
    and the holographic HUD panel."""

    def __init__(self, enabled: bool = False):
        self.enabled = False

    def set_state(self, state: str) -> None:
        pass

    def push_command(self, text: str) -> None:
        pass

    def set_current_action(self, text: str) -> None:
        pass

    def set_last_response(self, text: str) -> None:
        pass

    def set_memory_stats(self, text: str) -> None:
        pass

    def start(self) -> None:
        pass

    def stop(self) -> None:
        pass

    def update(self) -> None:
        pass
