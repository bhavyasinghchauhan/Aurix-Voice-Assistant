"""Controls the Electron sphere overlay from Python.

Launches the Electron app as a subprocess and sends state/audio updates
over WebSocket. Also receives click events from the sphere. Runs entirely
in a background thread so it never blocks the async voice loop.
"""
import json
import os
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Callable, Optional

from utils.logger import get_logger

logger = get_logger(__name__)

WS_PORT = 9734
_SPHERE_DIR = Path(__file__).parent / "electron-sphere"


class SphereController:
    """Manages the Electron sphere subprocess and WebSocket connection."""

    def __init__(self):
        self._proc: Optional[subprocess.Popen] = None
        self._ws = None
        self._lock = threading.Lock()
        self._running = False
        self._on_click: Optional[Callable] = None
        self._listen_thread: Optional[threading.Thread] = None

    def set_click_handler(self, handler: Callable) -> None:
        self._on_click = handler

    # ─── Lifecycle ──────────────────────────────────────────────────────

    def start(self) -> None:
        """Launch the Electron app and connect via WebSocket."""
        self._running = True
        thread = threading.Thread(target=self._launch_and_connect, daemon=True, name="sphere-ctrl")
        thread.start()
        logger.info("Sphere controller starting")

    def stop(self) -> None:
        """Shut down the sphere cleanly."""
        self._running = False
        self._send({"type": "quit"})
        time.sleep(0.3)
        with self._lock:
            if self._ws is not None:
                try:
                    self._ws.close()
                except Exception:
                    pass
                self._ws = None
            if self._proc is not None:
                try:
                    self._proc.terminate()
                    self._proc.wait(timeout=5)
                except Exception:
                    try:
                        self._proc.kill()
                    except Exception:
                        pass
                self._proc = None
        logger.info("Sphere controller stopped")

    # ─── Public API (thread-safe) ───────────────────────────────────────

    def set_state(self, state: str) -> None:
        """Send a state change (idle, listening, thinking, speaking, error)."""
        self._send({"type": "state", "state": state})

    def send_audio(self, low: float, mid: float, high: float, amp: float) -> None:
        """Forward audio frequency band levels to the sphere."""
        self._send({
            "type": "audio",
            "low": round(low, 3),
            "mid": round(mid, 3),
            "high": round(high, 3),
            "amp": round(amp, 3),
        })

    def send_goodbye(self) -> None:
        """Trigger the goodbye fade animation."""
        self._send({"type": "goodbye"})

    # ─── Internal ───────────────────────────────────────────────────────

    def _launch_and_connect(self) -> None:
        """Run in background thread: launch Electron, then connect WS."""
        npm_cmd = "npm.cmd" if sys.platform == "win32" else "npm"

        node_modules = _SPHERE_DIR / "node_modules"
        if not node_modules.exists():
            logger.info("Installing Electron sphere dependencies (first run)...")
            try:
                subprocess.run(
                    [npm_cmd, "install"],
                    cwd=str(_SPHERE_DIR),
                    check=True,
                    capture_output=True,
                )
            except Exception as e:
                logger.error(f"npm install failed: {e}")
                return

        npx_cmd = "npx.cmd" if sys.platform == "win32" else "npx"
        try:
            self._proc = subprocess.Popen(
                [npx_cmd, "electron", "."],
                cwd=str(_SPHERE_DIR),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            logger.info(f"Electron sphere launched (PID {self._proc.pid})")
        except FileNotFoundError:
            logger.error(
                "Cannot launch Electron sphere: npx/electron not found. "
                "Run: cd gui/electron-sphere && npm install"
            )
            return
        except Exception as e:
            logger.error(f"Failed to launch Electron sphere: {e}")
            return

        self._connect_ws()

    def _connect_ws(self) -> None:
        """Try to connect to the Electron WebSocket server with retries."""
        try:
            import websocket
        except ImportError:
            logger.error(
                "websocket-client not installed. Run: pip install websocket-client"
            )
            return

        url = f"ws://localhost:{WS_PORT}"
        for attempt in range(20):
            if not self._running:
                return
            try:
                ws = websocket.create_connection(url, timeout=2)
                with self._lock:
                    self._ws = ws
                logger.info(f"Connected to sphere WebSocket on attempt {attempt + 1}")
                self._start_listener()
                return
            except Exception:
                time.sleep(0.5)

        logger.warning("Could not connect to Electron sphere WebSocket after 10s")

    def _start_listener(self) -> None:
        """Start a thread that listens for messages FROM the Electron sphere."""
        self._listen_thread = threading.Thread(
            target=self._listen_loop, daemon=True, name="sphere-listen",
        )
        self._listen_thread.start()

    def _listen_loop(self) -> None:
        """Receive messages from Electron (click events, etc.)."""
        logger.debug("Sphere listener thread started")
        while self._running:
            with self._lock:
                ws = self._ws
            if ws is None:
                logger.debug("Sphere WS is None, listener exiting")
                break
            try:
                raw = ws.recv()
                if not raw:
                    continue
                msg = json.loads(raw)
                logger.debug(f"Sphere received message: {msg}")
                if msg.get("type") == "click":
                    logger.info("Sphere click received from Electron")
                    if self._on_click:
                        self._on_click()
                    else:
                        logger.warning("No click handler registered")
            except Exception as e:
                logger.debug(f"Sphere listener error: {e}")
                break
        logger.debug("Sphere listener thread exiting")

    def _send(self, msg: dict) -> None:
        """Send a JSON message to the Electron app. Silently drops if not connected."""
        with self._lock:
            if self._ws is None:
                return
            try:
                self._ws.send(json.dumps(msg))
            except Exception:
                self._ws = None
