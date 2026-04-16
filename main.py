"""AURIX entry point."""
import argparse
import asyncio
import os
import sys

import yaml
from dotenv import load_dotenv

# Load .env from the project root before anything else reads os.environ.
_ENV_PATH = os.path.join(os.path.dirname(__file__), ".env")
load_dotenv(_ENV_PATH)


def load_config() -> dict:
    config_path = os.path.join(os.path.dirname(__file__), "config", "settings.yaml")
    with open(config_path, "r") as f:
        config = yaml.safe_load(f) or {}
    return config


def _progress_bar(pct: int, width: int = 10) -> str:
    filled = int(width * pct / 100)
    return "\u2593" * filled + "\u2591" * (width - filled)


def _log_step(pct: int, label: str) -> None:
    bar = _progress_bar(pct)
    print(f"[INFO] {bar} {pct}% - {label}")


async def main() -> None:
    parser = argparse.ArgumentParser(description="AURIX voice assistant")
    parser.add_argument(
        "--gui", action="store_true",
        help="Launch the visual orb + HUD interface",
    )
    parser.add_argument(
        "--sphere", action="store_true",
        help="Launch the Electron 3D sphere overlay",
    )
    parser.add_argument(
        "--reset-memory", action="store_true",
        help="Clear the memory graph before starting (useful for testing)",
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show all debug logs in terminal",
    )
    parser.add_argument(
        "--silent", action="store_true",
        help="Start directly in silent (text) mode, skip mode selection",
    )
    parser.add_argument(
        "--speech", action="store_true",
        help="Start directly in speech mode, skip mode selection",
    )
    args = parser.parse_args()

    # Configure logging verbosity before any logger is created
    from utils.logger import set_verbose
    if args.verbose:
        set_verbose(True)

    print()
    print("[INFO] AURIX Initialization")
    print()

    config = load_config()

    if args.gui:
        config["gui_enabled"] = True
    if args.sphere:
        config["sphere_enabled"] = True

    # ── Determine mode ──────────────────────────────────────────────
    chosen_mode = None

    if args.silent:
        chosen_mode = "silent"
    elif args.speech:
        chosen_mode = "speech"
    elif config.get("sphere_enabled", False):
        # Show startup GUI with loading + mode selection
        _log_step(10, "Preparing startup screen...")

        from gui.startup_screen import StartupScreen
        import threading

        screen = StartupScreen()

        LOADING_STEPS = [
            (20, "Loading voice models..."),
            (40, "Initializing LLM..."),
            (60, "Starting memory system..."),
            (80, "Launching GUI..."),
        ]

        def _feed_progress():
            screen.wait_for_window()
            import time
            for pct, label in LOADING_STEPS:
                _log_step(pct, label)
                screen.set_progress(pct, label)
                time.sleep(0.5)
            _log_step(100, "Ready!")
            screen.finish_loading()

        feeder = threading.Thread(target=_feed_progress, daemon=True)
        feeder.start()

        chosen_mode = screen.run()
    else:
        chosen_mode = "speech"

    _log_step(100, "Ready!")
    print(f"[INFO] Mode selected: {chosen_mode.upper()}")
    print()

    # ── Import engine after logging is configured ───────────────────
    from core.engine import AurixEngine

    engine = AurixEngine(config, mode=chosen_mode)

    if args.reset_memory:
        engine.memory.clear()
        graph_path = config.get("graph_path", "data/graph.pkl")
        full_path = os.path.join(os.path.dirname(__file__), graph_path)
        if os.path.exists(full_path):
            os.remove(full_path)
            print(f"[INFO] Deleted {full_path}")
        print("[INFO] Memory graph reset.")

    print(f"[INFO] AURIX started successfully | Mode: {chosen_mode.upper()}")
    print()

    await engine.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n[INFO] AURIX terminated by user.")
