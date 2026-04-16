"""Media playback and volume control."""
from utils.error_handler import ToolExecutionError
from utils.logger import get_logger

logger = get_logger(__name__)


VALID_ACTIONS = {"play", "pause", "next", "previous", "volume_up", "volume_down"}


async def control_media(action: str) -> dict:
    """Send a media key event to the OS."""
    if action not in VALID_ACTIONS:
        raise ToolExecutionError(f"Invalid media action: {action}")

    try:
        import keyboard
    except ImportError as e:
        raise ToolExecutionError("keyboard package not installed") from e

    key_map = {
        "play": "play/pause media",
        "pause": "play/pause media",
        "next": "next track",
        "previous": "previous track",
        "volume_up": "volume up",
        "volume_down": "volume down",
    }
    key = key_map[action]
    try:
        keyboard.send(key)
        logger.info(f"Sent media key: {action}")
        return {"action": action, "key": key}
    except Exception as e:
        raise ToolExecutionError(f"Failed to send media key {action}: {e}") from e
