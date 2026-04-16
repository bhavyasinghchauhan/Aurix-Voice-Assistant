"""Verify AURIX branding: wake word, prompts, and goodnight detection."""
import re
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

PASS = 0
FAIL = 0


def check(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    if condition:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        msg = f"  [FAIL] {name}"
        if detail:
            msg += f" — {detail}"
        print(msg)


# ── 1. Wake word config ────────────────────────────────────────────────

print("\n=== Wake Word Config ===")

import yaml
with open("config/settings.yaml", "r") as f:
    cfg = yaml.safe_load(f)

wake_word = cfg.get("wake_word", "")
check(
    "settings.yaml wake_word is 'hey_aurix'",
    wake_word == "hey_aurix",
    f"got '{wake_word}'",
)

# ── 2. Wake word detector knows 'hey_aurix' ───────────────────────────

print("\n=== Wake Word Detector ===")

from voice.wake_word_detector import BUILTIN_MODELS

check(
    "'hey_aurix' in BUILTIN_MODELS",
    "hey_aurix" in BUILTIN_MODELS,
    f"keys: {sorted(BUILTIN_MODELS)}",
)
check(
    "'aurix' in BUILTIN_MODELS",
    "aurix" in BUILTIN_MODELS,
)
check(
    "hey_aurix maps to hey_jarvis model",
    BUILTIN_MODELS.get("hey_aurix") == "hey_jarvis",
    f"got '{BUILTIN_MODELS.get('hey_aurix')}'",
)

# ── 3. Goodnight detection ─────────────────────────────────────────────

print("\n=== Goodnight Detection ===")

from core.engine import GOODNIGHT_PATTERN

goodnight_tests = [
    ("goodnight aurix", True),
    ("goodbye aurix", True),
    ("shut down aurix", True),
    ("aurix goodnight", True),
    ("aurix goodbye", True),
    ("goodnight AURIX", True),
    ("hello aurix", False),
    ("open chrome", False),
]

for phrase, expected in goodnight_tests:
    match = bool(GOODNIGHT_PATTERN.search(phrase))
    check(
        f"'{phrase}' -> {'match' if expected else 'no match'}",
        match == expected,
        f"expected {expected}, got {match}",
    )

# ── 4. System prompt says AURIX, not Jarvis ───────────────────────────

print("\n=== System Prompt ===")

from llm.prompt_builder import SYSTEM_TEMPLATE

check(
    "Prompt contains 'AURIX'",
    "AURIX" in SYSTEM_TEMPLATE,
)
check(
    "Prompt does NOT say 'Jarvis-style'",
    "Jarvis-style" not in SYSTEM_TEMPLATE,
)
check(
    "Prompt says 'never refer to yourself as Jarvis'",
    "Jarvis" in SYSTEM_TEMPLATE and "never refer to yourself as Jarvis" in SYSTEM_TEMPLATE,
)
check(
    "Prompt includes limitation about changing settings",
    "CANNOT change wake words" in SYSTEM_TEMPLATE,
)

# ── 5. LLM smart model ────────────────────────────────────────────────

print("\n=== LLM Model Config ===")

from llm.claude_interface import SMART_MODEL, FAST_MODEL

check(
    "SMART_MODEL is llama3.2:1b",
    SMART_MODEL == "llama3.2:1b",
    f"got '{SMART_MODEL}'",
)
check(
    "FAST_MODEL is llama3.2:3b",
    FAST_MODEL == "llama3.2:3b",
    f"got '{FAST_MODEL}'",
)

# ── 6. Gmail tool descriptions ─────────────────────────────────────────

print("\n=== Gmail Tool Descriptions ===")

from llm.claude_interface import ClaudeInterface

cli = ClaudeInterface.__new__(ClaudeInterface)
tools = cli._load_tool_definitions()
tool_map = {t["function"]["name"]: t["function"]["description"] for t in tools}

check(
    "check_unread_count mentions 'check my email'",
    "check my email" in tool_map.get("check_unread_count", ""),
)
check(
    "web_search says NOT for email",
    "NOT use this for email" in tool_map.get("web_search", ""),
)

# ── Summary ────────────────────────────────────────────────────────────

print(f"\n{'='*40}")
print(f"Results: {PASS} passed, {FAIL} failed")
if FAIL > 0:
    print("Some checks FAILED — review above.")
    sys.exit(1)
else:
    print("All checks PASSED!")
    sys.exit(0)
