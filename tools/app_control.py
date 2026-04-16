"""Launch / close applications."""
import os
import shutil
import subprocess
import sys
from typing import List, Optional

import psutil

from utils.error_handler import ToolExecutionError
from utils.logger import get_logger

logger = get_logger(__name__)


# Windows paths to try for apps that aren't on PATH. First existing path wins.
_WIN_CHROME_PATHS = [
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
]

_WIN_SPOTIFY_PATHS = [
    os.path.expandvars(r"%APPDATA%\Spotify\Spotify.exe"),
    os.path.expandvars(r"%LOCALAPPDATA%\Microsoft\WindowsApps\Spotify.exe"),
]

_WIN_BRAVE_PATHS = [
    r"C:\Program Files\BraveSoftware\Brave-Browser\Application\brave.exe",
    r"C:\Program Files (x86)\BraveSoftware\Brave-Browser\Application\brave.exe",
    os.path.expandvars(r"%LOCALAPPDATA%\BraveSoftware\Brave-Browser\Application\brave.exe"),
]

# Friendly name -> per-platform candidate list. Each entry is a list of paths
# to try in order; the first one that exists on disk (or is found on PATH) wins.
APP_ALIASES = {
    "chrome": {
        "win32": _WIN_CHROME_PATHS,
        "linux": ["google-chrome", "google-chrome-stable", "chromium-browser"],
        "darwin": ["Google Chrome"],
    },
    "brave": {
        "win32": _WIN_BRAVE_PATHS,
        "linux": ["brave-browser", "brave"],
        "darwin": ["Brave Browser"],
    },
    "vscode": {
        "win32": ["code.cmd"],
        "linux": ["code"],
        "darwin": ["code"],
    },
    "spotify": {
        "win32": _WIN_SPOTIFY_PATHS + ["spotify.exe"],
        "linux": ["spotify"],
        "darwin": ["Spotify"],
    },
    "notepad": {"win32": ["notepad.exe"]},
    "task_manager": {"win32": ["taskmgr.exe", "taskmgr"]},
    "calculator": {"win32": ["calc.exe"], "linux": ["gnome-calculator"], "darwin": ["Calculator"]},
    "explorer": {"win32": ["explorer.exe"]},
}

# Aliases that map user phrasing -> canonical APP_ALIASES key.
APP_NAME_ALIASES = {
    "brave browser": "brave",
    "brave-browser": "brave",
    "task manager": "task_manager",
    "taskmanager": "task_manager",
    "taskmgr": "task_manager",
    "google chrome": "chrome",
    "chrome browser": "chrome",
    "visual studio code": "vscode",
    "vs code": "vscode",
    "code": "vscode",
    "file explorer": "explorer",
    "windows explorer": "explorer",
    "calc": "calculator",
}


def _first_existing(candidates: List[str]) -> Optional[str]:
    """Return the first candidate that exists as a file or is found on PATH."""
    for path in candidates:
        if os.path.isfile(path):
            return path
        found = shutil.which(path)
        if found:
            return found
    return None


def _resolve_binary(app_name: str) -> Optional[str]:
    key = app_name.lower().strip()
    key = APP_NAME_ALIASES.get(key, key)
    if key in APP_ALIASES:
        candidates = APP_ALIASES[key].get(sys.platform, [])
        if candidates:
            found = _first_existing(candidates)
            if found:
                return found
    return shutil.which(app_name) or shutil.which(key)


_DISPLAY_NAMES = {
    "chrome": "Chrome",
    "brave": "Brave Browser",
    "vscode": "VS Code",
    "spotify": "Spotify",
    "notepad": "Notepad",
    "task_manager": "Task Manager",
    "calculator": "Calculator",
    "explorer": "File Explorer",
}


async def open_application(app_name: str) -> dict:
    """Launch an application by friendly name."""
    binary = _resolve_binary(app_name)
    if binary is None:
        raise ToolExecutionError(f"Could not resolve application: {app_name}")

    canonical = APP_NAME_ALIASES.get(app_name.lower().strip(), app_name.lower().strip())
    display = _DISPLAY_NAMES.get(canonical, app_name.title())

    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", "-a", binary])
        else:
            subprocess.Popen([binary])
        logger.info(f"Launched {display} ({binary})")
        summary = f"Opened {display}"
        return {
            "app": app_name,
            "display": display,
            "binary": binary,
            "launched": True,
            "summary": summary,
            "brief": summary,
        }
    except Exception as e:
        raise ToolExecutionError(f"Failed to launch {app_name}: {e}") from e


async def close_application(app_name: str) -> dict:
    """Terminate processes matching the given app name."""
    target = app_name.lower()
    killed = 0
    for proc in psutil.process_iter(["name", "pid"]):
        try:
            name = (proc.info.get("name") or "").lower()
            if target in name:
                proc.terminate()
                killed += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    if killed == 0:
        raise ToolExecutionError(f"No running process matches {app_name}")
    return {"app": app_name, "killed": killed}
