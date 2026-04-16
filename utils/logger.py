"""Centralized logging setup for AURIX."""
import logging
import os
from pathlib import Path

_LOG_LEVEL = os.environ.get("AURIX_LOG_LEVEL", "INFO").upper()
_LOG_PATH = Path(os.environ.get("AURIX_LOG_PATH", "logs/aurix.log"))

_initialized = False
_verbose = False


def set_verbose(enabled: bool) -> None:
    """Call before any get_logger() to enable DEBUG on the console."""
    global _verbose, _initialized
    _verbose = enabled
    if _initialized:
        root = logging.getLogger("aurix")
        for h in root.handlers:
            if isinstance(h, logging.StreamHandler) and not isinstance(h, logging.FileHandler):
                h.setLevel(logging.DEBUG if enabled else logging.INFO)


def _init_root_logger() -> None:
    global _initialized
    if _initialized:
        return

    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)

    fmt = "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    clean_fmt = "[%(levelname)s] %(message)s"
    formatter = logging.Formatter(fmt)
    console_formatter = logging.Formatter(clean_fmt)

    root = logging.getLogger("aurix")
    root.setLevel(logging.DEBUG)
    root.propagate = False

    if not root.handlers:
        stream = logging.StreamHandler()
        stream.setFormatter(console_formatter)
        stream.setLevel(logging.DEBUG if _verbose else logging.INFO)
        root.addHandler(stream)

        try:
            file_handler = logging.FileHandler(_LOG_PATH, encoding="utf-8")
            file_handler.setFormatter(formatter)
            file_handler.setLevel(logging.DEBUG)
            root.addHandler(file_handler)
        except OSError:
            pass

    _initialized = True


def get_logger(name: str) -> logging.Logger:
    _init_root_logger()
    return logging.getLogger(f"aurix.{name}")
