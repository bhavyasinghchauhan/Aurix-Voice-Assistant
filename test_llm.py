"""
LLM integration smoke test.

Verifies the Ollama plumbing without touching audio/voice components:
  1. Checks that the Ollama daemon is reachable
  2. Constructs a ClaudeInterface
  3. Sends the test command "open chrome"
  4. Prints the response, tool calls, and which model handled it

Run from the project root:
    python test_llm.py
"""
import asyncio
import json
import sys
from pathlib import Path

# Force UTF-8 stdout (Windows cp1252 console can't handle some chars)
if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


async def main() -> int:
    section("1. Checking Ollama daemon")

    try:
        import ollama as _ollama
    except ImportError:
        print("  FAIL: ollama package not installed")
        print("        pip install ollama")
        return 1

    try:
        _ollama.list()
        print("  OK   Ollama daemon is reachable")
    except Exception as e:
        print(f"  FAIL: cannot reach Ollama daemon: {e}")
        print("        Make sure Ollama is running (ollama serve)")
        return 1

    section("2. Constructing ClaudeInterface")

    sys.path.insert(0, str(Path(__file__).parent))
    try:
        from llm.claude_interface import ClaudeInterface, FAST_MODEL, SMART_MODEL
    except ImportError as e:
        print(f"  FAIL: cannot import ClaudeInterface: {e}")
        return 1

    try:
        llm = ClaudeInterface()
    except Exception as e:
        print(f"  FAIL: ClaudeInterface init: {e}")
        return 1

    print(f"  OK   fast_model  = {llm.fast_model}")
    print(f"  OK   smart_model = {llm.smart_model}")

    section("3. Sending test command")

    test_command = "open chrome"
    print(f"  command: {test_command!r}")

    routed_model = llm.complexity.pick_model(test_command)
    is_complex = llm.complexity.is_complex(test_command)
    print(f"  router : is_complex={is_complex} -> {routed_model}")

    try:
        response = await llm.process_command(
            user_input=test_command,
            context=[],
            system_state="Idle",
        )
    except Exception as e:
        print(f"\n  FAIL: Ollama call raised {type(e).__name__}: {e}")
        return 1

    section("4. Response")

    model_used = response.get("model_used", "?")
    text = response.get("response", "")
    tool_calls = response.get("tool_calls", [])
    needs_confirm = response.get("requires_confirmation", False)

    is_fast = model_used == FAST_MODEL
    is_smart = model_used == SMART_MODEL
    label = "FAST" if is_fast else "SMART" if is_smart else "OTHER"

    print(f"  model_used  : {model_used}  [{label}]")
    print(f"  needs_confirm: {needs_confirm}")
    print()
    print(f"  text response:")
    if text:
        for line in text.splitlines() or [text]:
            print(f"    {line}")
    else:
        print("    (empty)")
    print()
    print(f"  tool_calls ({len(tool_calls)}):")
    if tool_calls:
        for i, call in enumerate(tool_calls, 1):
            print(f"    [{i}] tool: {call.get('tool')}")
            params = call.get("params", {})
            if params:
                params_str = json.dumps(params, indent=8)
                lines = params_str.splitlines()
                print(f"        params: {lines[0]}")
                for line in lines[1:]:
                    print(f"        {line}")
            else:
                print(f"        params: {{}}")
    else:
        print("    (none — the engine would escalate to the smart model)")

    section("5. Verdict")

    expected_tool = "open_application"
    got_expected = any(c.get("tool") == expected_tool for c in tool_calls)

    if got_expected:
        print(f"  PASS: got expected tool call '{expected_tool}'")
        return 0

    print(f"  WARN: did not get '{expected_tool}' tool call")
    print(f"        This is a soft failure -- the LLM may have responded")
    print(f"        with a clarification question instead.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
