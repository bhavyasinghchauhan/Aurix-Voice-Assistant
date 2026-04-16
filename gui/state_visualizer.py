"""Maps system state to visual feedback."""
from gui.hud_panel import HUDPanel
from gui.orb_renderer import OrbGUI


class StateVisualizer:
    """Coordinates orb + HUD updates from a single state change."""

    def __init__(self, orb: OrbGUI, hud: HUDPanel):
        self.orb = orb
        self.hud = hud

    def set_state(self, state: str) -> None:
        self.orb.set_state(state)

    def show_command(self, text: str) -> None:
        self.hud.set_command(text)

    def show_response(self, text: str) -> None:
        self.hud.set_response(text)

    def show_action(self, text: str) -> None:
        self.hud.set_action(text)

    def show_memory_stats(self, text: str) -> None:
        self.hud.set_memory_stats(text)

    def update(self) -> None:
        pass
