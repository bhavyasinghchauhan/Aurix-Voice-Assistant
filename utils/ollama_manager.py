"""Auto-start and manage the Ollama daemon for AURIX."""
import shutil
import subprocess
import sys
import time
from typing import Optional

import requests

from utils.logger import get_logger

logger = get_logger(__name__)

OLLAMA_API = "http://localhost:11434"
HEALTH_ENDPOINT = f"{OLLAMA_API}/api/tags"
STARTUP_TIMEOUT = 30
POLL_INTERVAL = 0.5


class OllamaManager:
    """Checks if Ollama is running, launches it if not, and shuts it down on exit."""

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._we_started_it = False

    def is_running(self) -> bool:
        try:
            resp = requests.get(HEALTH_ENDPOINT, timeout=2)
            return resp.status_code == 200
        except Exception:
            return False

    def ensure_running(self) -> bool:
        """Return True if Ollama is reachable (already running or just launched)."""
        if self.is_running():
            logger.info("Ollama is already running")
            return True

        logger.info("Ollama not detected — attempting auto-start...")
        return self._launch()

    def _launch(self) -> bool:
        ollama_bin = self._find_ollama()
        if ollama_bin is None:
            logger.error(
                "Cannot find ollama executable. "
                "Install from https://ollama.com and make sure it's on PATH."
            )
            return False

        try:
            self._proc = subprocess.Popen(
                [ollama_bin, "serve"],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
            )
            self._we_started_it = True
            logger.info(f"Launched Ollama daemon (PID {self._proc.pid})")
        except Exception as e:
            logger.error(f"Failed to launch Ollama: {e}")
            return False

        return self._wait_for_ready()

    def _wait_for_ready(self) -> bool:
        elapsed = 0.0
        while elapsed < STARTUP_TIMEOUT:
            if self.is_running():
                logger.info(f"Ollama ready after {elapsed:.1f}s")
                return True
            time.sleep(POLL_INTERVAL)
            elapsed += POLL_INTERVAL

        logger.error(f"Ollama did not become ready within {STARTUP_TIMEOUT}s")
        return False

    @staticmethod
    def _find_ollama() -> Optional[str]:
        found = shutil.which("ollama")
        if found:
            return found

        if sys.platform == "win32":
            import os
            candidates = [
                os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "Ollama", "ollama.exe"),
                os.path.join(os.environ.get("ProgramFiles", ""), "Ollama", "ollama.exe"),
                os.path.join(os.environ.get("USERPROFILE", ""), "AppData", "Local", "Programs", "Ollama", "ollama.exe"),
            ]
            for path in candidates:
                if path and os.path.isfile(path):
                    return path

        return None

    def shutdown(self) -> None:
        """Stop the Ollama daemon only if we started it."""
        if not self._we_started_it or self._proc is None:
            return

        logger.info("Shutting down Ollama daemon (we started it)...")
        try:
            self._proc.terminate()
            self._proc.wait(timeout=10)
            logger.info("Ollama daemon stopped")
        except subprocess.TimeoutExpired:
            logger.warning("Ollama didn't stop gracefully — killing")
            try:
                self._proc.kill()
                self._proc.wait(timeout=5)
            except Exception:
                pass
        except Exception as e:
            logger.error(f"Error stopping Ollama: {e}")
        finally:
            self._proc = None
            self._we_started_it = False
