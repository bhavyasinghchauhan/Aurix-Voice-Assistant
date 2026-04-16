"""System control tools (shutdown, restart AURIX)."""
import asyncio
import os
import signal

from utils.logger import get_logger

logger = get_logger(__name__)

_shutdown_callback = None


def register_shutdown_callback(callback):
    global _shutdown_callback
    _shutdown_callback = callback


async def shutdown_aurix(**kwargs):
    logger.info("Shutdown requested via tool call")
    if _shutdown_callback is not None:
        await _shutdown_callback()
    else:
        os.kill(os.getpid(), signal.SIGTERM)
    return {"success": True, "message": "AURIX shutting down"}
