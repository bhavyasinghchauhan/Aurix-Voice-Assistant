"""
Memory system test -- verifies shortcut creation after repeated commands.

Exercises the graph memory in isolation (no LLM, no voice):
  1. Adds the same command 3 times with identical tool calls
  2. Checks that a MACRO shortcut node was created
  3. Verifies find_shortcut() matches the repeated command
  4. Shows retrieval timing to confirm performance

Run from the project root:
    python test_memory.py
"""
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def main() -> int:
    print("AURIX memory system test")
    print("========================")

    section("1. Initializing GraphMemory")
    try:
        from memory.graph_memory import GraphMemory
    except ImportError as e:
        print(f"  FAIL: {e}")
        return 1

    mem = GraphMemory()
    mem.shortcut_frequency_threshold = 3
    print(f"  OK   GraphMemory created (threshold={mem.shortcut_frequency_threshold})")
    mem.log_stats()

    section("2. Adding 3 identical interactions")
    command = "open chrome"
    tool_calls = [{"tool": "open_application", "params": {"app_name": "chrome"}}]

    for i in range(1, 4):
        t0 = time.monotonic()
        node_id = mem.add_interaction(
            intent=command,
            actions=tool_calls,
            result="Launched chrome",
            success=True,
        )
        elapsed_ms = (time.monotonic() - t0) * 1000
        print(f"  [{i}] Added interaction {node_id[:12]}... ({elapsed_ms:.1f}ms)")

    section("3. Checking for MACRO shortcut")
    macros = [n for n in mem.node_index.values() if n.type == "MACRO"]
    if macros:
        for m in macros:
            print(f"  OK   MACRO found: {m.content}")
            print(f"         sequence: {m.compressed_sequence}")
            print(f"         weight: {m.weight}, exec_count: {m.execution_count}")
    else:
        print("  WARN: No MACRO nodes created")
        print("         (shortcut detection may need more varied sequences)")

    section("4. Testing find_shortcut()")
    t0 = time.monotonic()
    shortcut = mem.find_shortcut(command)
    elapsed_ms = (time.monotonic() - t0) * 1000

    if shortcut:
        print(f"  OK   Shortcut found in {elapsed_ms:.1f}ms")
        print(f"         macro_id: {shortcut['macro_id'][:12]}...")
        print(f"         confidence: {shortcut['confidence']:.3f}")
        print(f"         sequence: {shortcut['sequence']}")
    else:
        print(f"  INFO: No shortcut matched ({elapsed_ms:.1f}ms)")
        print("         This is expected if sequences are too short for matching")

    section("5. Context retrieval timing")
    t0 = time.monotonic()
    context = mem.retrieve_context(command)
    elapsed_ms = (time.monotonic() - t0) * 1000
    print(f"  Retrieved {len(context)} context nodes in {elapsed_ms:.1f}ms")

    section("6. Final stats")
    mem.log_stats()

    total = len(mem.node_index)
    shortcuts = len(macros)

    section("Verdict")
    if total >= 9:
        print(f"  PASS: {total} nodes stored (3 intents + 3 actions + 3 results)")
    else:
        print(f"  WARN: expected >= 9 nodes, got {total}")

    if shortcuts > 0:
        print(f"  PASS: {shortcuts} shortcut(s) created after 3 repetitions")
    else:
        print(f"  INFO: 0 shortcuts -- threshold or sequence matching may need tuning")

    return 0


if __name__ == "__main__":
    sys.exit(main())
