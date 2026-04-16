"""Custom exceptions and graceful-degradation helpers."""
from typing import Any, Callable, Coroutine

from utils.logger import get_logger

logger = get_logger(__name__)


class AurixError(Exception):
    """Base exception for AURIX errors."""


class VoiceError(AurixError):
    """Voice processing errors."""


class LLMError(AurixError):
    """LLM API errors."""


class ToolExecutionError(AurixError):
    """Tool execution errors."""


async def safe_execute(
    fn: Callable[..., Coroutine[Any, Any, Any]],
    *args,
    fallback_message: str = "Something went wrong",
    **kwargs,
) -> dict:
    """Run an async function with structured error reporting."""
    try:
        result = await fn(*args, **kwargs)
        return {"success": True, "result": result}
    except PermissionError:
        logger.warning("Permission denied")
        return {"success": False, "error": "permission_denied", "message": "I don't have permission for that"}
    except ToolExecutionError as e:
        logger.error(f"Tool execution error: {e}")
        return {"success": False, "error": "tool_failed", "message": str(e)}
    except AurixError as e:
        logger.error(f"AURIX error: {e}")
        return {"success": False, "error": e.__class__.__name__, "message": str(e)}
    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return {"success": False, "error": "unexpected", "message": fallback_message}
