"""
AURIX setup verification script.

Run before `python main.py` to confirm:
  1. The .env file loads and ANTHROPIC_API_KEY is present
  2. Internal AURIX modules import cleanly
  3. Third-party dependencies are installed (with a checklist of what's missing)

Usage:
    python test_setup.py
"""
import importlib
import os
import sys
from pathlib import Path

# Force UTF-8 stdout on Windows so we never blow up on a stray unicode char.
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ANSI color codes — only enabled when the terminal looks capable.
_ANSI = sys.stdout.isatty() and os.environ.get("NO_COLOR") is None
if _ANSI and os.name == "nt":
    try:
        import colorama  # type: ignore

        colorama.just_fix_windows_console()
    except ImportError:
        _ANSI = False

GREEN = "\033[92m" if _ANSI else ""
RED = "\033[91m" if _ANSI else ""
YELLOW = "\033[93m" if _ANSI else ""
DIM = "\033[2m" if _ANSI else ""
RESET = "\033[0m" if _ANSI else ""


def ok(msg: str) -> None:
    print(f"  {GREEN}[OK]{RESET}   {msg}")


def fail(msg: str) -> None:
    print(f"  {RED}[FAIL]{RESET} {msg}")


def warn(msg: str) -> None:
    print(f"  {YELLOW}[WARN]{RESET} {msg}")


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


# ─── 1. Environment ──────────────────────────────────────────────────────────

def check_env() -> bool:
    section("1. Environment (Ollama)")

    # .env is optional now (no API key needed), but we still load it for
    # any other env vars the user might set.
    env_path = Path(__file__).parent / ".env"
    if env_path.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_path)
            ok(f"Loaded .env from {env_path}")
        except ImportError:
            warn("python-dotenv not installed -- .env will be ignored")
    else:
        ok(".env not present (not required for Ollama)")

    # Check that the Ollama daemon is reachable
    try:
        import ollama as _ollama

        _ollama.list()
        ok("Ollama daemon is reachable on localhost")
    except ImportError:
        fail("ollama package not installed -- run: pip install ollama")
        return False
    except Exception as e:
        fail(f"Cannot reach Ollama daemon: {e}")
        warn("Make sure Ollama is running: ollama serve")
        return False

    return True


# ─── 2. Internal modules ─────────────────────────────────────────────────────

INTERNAL_MODULES = [
    "core.state_manager",
    "core.engine",
    "voice.audio_utils",
    "voice.wake_word_detector",
    "voice.speech_to_text",
    "voice.text_to_speech",
    "llm.claude_interface",
    "llm.prompt_builder",
    "llm.tool_parser",
    "memory.node",
    "memory.graph_memory",
    "memory.embeddings",
    "memory.retrieval",
    "memory.optimization",
    "tools.executor",
    "tools.app_control",
    "tools.browser_automation",
    "tools.file_system",
    "tools.media_control",
    "tools.calendar_reminders",
    "automation.recorder",
    "automation.cycle_manager",
    "automation.trigger_engine",
    "gui.orb_renderer",
    "gui.hud_panel",
    "gui.state_visualizer",
    "utils.logger",
    "utils.error_handler",
    "utils.performance",
]


def check_internal() -> tuple[int, int]:
    section("2. AURIX modules")

    sys.path.insert(0, str(Path(__file__).parent))
    passed = 0
    failed = 0
    failures: list[tuple[str, str]] = []

    for mod_name in INTERNAL_MODULES:
        try:
            importlib.import_module(mod_name)
            passed += 1
        except Exception as e:
            failed += 1
            failures.append((mod_name, f"{type(e).__name__}: {e}"))

    print(f"  {passed}/{len(INTERNAL_MODULES)} modules imported")
    for name, err in failures:
        fail(f"{name}  ->  {err}")
    return passed, failed


# ─── 3. Third-party dependencies ─────────────────────────────────────────────

# (import_name, pip_name, category, required_for)
DEPS = [
    # Core
    ("ollama", "ollama", "core", "Ollama local LLM"),
    ("yaml", "pyyaml", "core", "config loading"),
    ("dotenv", "python-dotenv", "core", "loading .env"),
    # Voice
    ("openwakeword", "openwakeword", "voice", "wake word detection"),
    ("speech_recognition", "speechrecognition", "voice", "STT"),
    ("gtts", "gtts", "voice", "TTS synthesis"),
    ("pyaudio", "pyaudio", "voice", "microphone capture"),
    # Memory / ML
    ("networkx", "networkx", "memory", "graph storage"),
    ("sentence_transformers", "sentence-transformers", "memory", "embeddings"),
    ("numpy", "numpy", "memory", "vector math"),
    # Tools / OS
    ("psutil", "psutil", "tools", "process listing"),
    ("pyautogui", "pyautogui", "tools", "GUI automation"),
    ("keyboard", "keyboard", "tools", "media keys + recording"),
    ("mouse", "mouse", "tools", "macro recording"),
    ("selenium", "selenium", "tools", "browser automation"),
    ("requests", "requests", "tools", "HTTP requests (weather, search)"),
    ("bs4", "beautifulsoup4", "tools", "web search HTML parsing"),
    # Gmail
    ("google.auth", "google-auth", "gmail", "Gmail API auth"),
    ("google_auth_oauthlib", "google-auth-oauthlib", "gmail", "Gmail OAuth2 flow"),
    ("googleapiclient", "google-api-python-client", "gmail", "Gmail API client"),
    # GUI
    ("pygame", "pygame", "gui", "orb renderer"),
    # Windows-only
    ("pygetwindow", "pygetwindow", "windows", "active window tracking"),
    ("win32gui", "pywin32", "windows", "Windows OS hooks"),
]


def check_deps() -> tuple[int, int]:
    section("3. Third-party dependencies")

    on_windows = sys.platform == "win32"
    installed = 0
    missing: list[tuple[str, str, str, str]] = []

    for import_name, pip_name, category, purpose in DEPS:
        if category == "windows" and not on_windows:
            print(f"  {DIM}[skip]{RESET} {pip_name}  ({purpose} — non-Windows)")
            continue
        try:
            importlib.import_module(import_name)
            installed += 1
            ok(f"{pip_name:<22} ({purpose})")
        except ImportError:
            missing.append((import_name, pip_name, category, purpose))

    print()
    if missing:
        print(f"  {RED}{len(missing)} missing dependencies:{RESET}")
        for _, pip_name, category, purpose in missing:
            tag = f"[{category}]"
            print(f"    {RED}x{RESET} {tag:<11} {pip_name:<22} - {purpose}")
        print()
        print(f"  Install with:")
        print(f"    pip install {' '.join(d[1] for d in missing)}")
    else:
        print(f"  {GREEN}All dependencies installed{RESET}")

    return installed, len(missing)


# ─── Main ────────────────────────────────────────────────────────────────────

def main() -> int:
    print("AURIX setup verification\n" + "=" * 24)

    env_ok = check_env()
    int_passed, int_failed = check_internal()
    dep_installed, dep_missing = check_deps()

    section("Summary")
    print(f"  Environment:    {'OK' if env_ok else 'FAIL'}")
    print(f"  AURIX modules:  {int_passed} ok / {int_failed} failed")
    print(f"  Dependencies:   {dep_installed} installed / {dep_missing} missing")
    print()

    if env_ok and int_failed == 0 and dep_missing == 0:
        print(f"{GREEN}AURIX is ready to run.{RESET}  Try:  python main.py")
        return 0

    print(f"{YELLOW}Setup incomplete — see issues above.{RESET}")
    if dep_missing > 0:
        print("  Most likely fix: pip install -r requirements.txt")
    return 1


if __name__ == "__main__":
    sys.exit(main())
