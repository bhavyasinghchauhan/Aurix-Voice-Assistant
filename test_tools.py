"""
Test suite for the 5 new AURIX tools.

Exercises each tool in isolation (no LLM, no voice):
  1. Weather   - fetch weather via wttr.in
  2. System    - read CPU/RAM/disk/battery
  3. Web search - search Google for a query
  4. Notes     - create, list, read a note
  5. Timer     - set and verify a short timer

Run from the project root:
    python test_tools.py
    python test_tools.py --skip-network   (skip weather + web search)
"""
import argparse
import asyncio
import shutil
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

sys.path.insert(0, str(Path(__file__).parent))

passed = 0
failed = 0


def section(title: str) -> None:
    print(f"\n{title}")
    print("-" * len(title))


def ok(msg: str) -> None:
    global passed
    passed += 1
    print(f"  [OK]   {msg}")


def fail(msg: str) -> None:
    global failed
    failed += 1
    print(f"  [FAIL] {msg}")


def skip(msg: str) -> None:
    print(f"  [SKIP] {msg}")


# ── 1. Weather ──────────────────────────────────────────────────────────────

async def test_weather(skip_network: bool) -> None:
    section("1. Weather (wttr.in)")
    if skip_network:
        skip("--skip-network flag set")
        return

    try:
        from tools.weather import get_weather
    except ImportError as e:
        fail(f"import error: {e}")
        return

    try:
        result = await get_weather("London")
        if result.get("temperature_c"):
            ok(f"London: {result['summary']}")
        else:
            fail(f"No temperature in response: {result}")
    except Exception as e:
        fail(f"get_weather('London') raised {type(e).__name__}: {e}")

    try:
        result = await get_weather("")
        if result.get("location"):
            ok(f"Auto-detect location: {result['location']}")
        else:
            fail(f"Auto-detect returned no location: {result}")
    except Exception as e:
        fail(f"get_weather('') raised {type(e).__name__}: {e}")


# ── 2. System info ──────────────────────────────────────────────────────────

async def test_system_info() -> None:
    section("2. System Info")

    try:
        from tools.system_info import get_system_info
    except ImportError as e:
        fail(f"import error: {e}")
        return

    try:
        result = await get_system_info()
        ok(f"CPU: {result['cpu_percent']}%")
        ok(f"RAM: {result['ram_percent']}% ({result['ram_used_gb']}/{result['ram_total_gb']} GB)")
        ok(f"Disk: {result['disk_percent']}%")
        if result.get("battery_percent") is not None:
            plug = "plugged" if result["battery_plugged"] else "battery"
            ok(f"Battery: {result['battery_percent']}% ({plug})")
        else:
            skip("No battery detected (desktop)")
    except Exception as e:
        fail(f"get_system_info() raised {type(e).__name__}: {e}")


# ── 3. Web search ──────────────────────────────────────────────────────────

async def test_web_search(skip_network: bool) -> None:
    section("3. Web Search")
    if skip_network:
        skip("--skip-network flag set")
        return

    try:
        from tools.web_search import web_search
    except ImportError as e:
        fail(f"import error: {e}")
        return

    try:
        result = await web_search("Python programming language")
        count = len(result.get("results", []))
        if count > 0:
            ok(f"Got {count} results for 'Python programming language'")
            for r in result["results"][:2]:
                print(f"           {r['title'][:60]}")
        else:
            fail("No results returned (Google may have blocked the request)")
    except Exception as e:
        fail(f"web_search() raised {type(e).__name__}: {e}")


# ── 4. Notes ────────────────────────────────────────────────────────────────

async def test_notes() -> None:
    section("4. Notes")

    try:
        from tools.notes import create_note, list_notes, read_note, NOTES_DIR
    except ImportError as e:
        fail(f"import error: {e}")
        return

    test_dir = NOTES_DIR
    created_files = []

    try:
        result = await create_note("Test note from test_tools.py", title="test_note")
        filename = result.get("file", "")
        if filename:
            ok(f"Created: {filename}")
            created_files.append(filename)
        else:
            fail(f"create_note returned no filename: {result}")
            return

        result = await list_notes()
        count = result.get("count", 0)
        if count > 0:
            ok(f"Listed {count} note(s)")
        else:
            fail("list_notes returned 0 notes after creating one")

        result = await read_note(filename)
        content = result.get("content", "")
        if "Test note" in content:
            ok(f"Read back: '{content[:50]}'")
        else:
            fail(f"read_note content mismatch: {content!r}")

    except Exception as e:
        fail(f"Notes test raised {type(e).__name__}: {e}")
    finally:
        for f in created_files:
            try:
                (test_dir / f).unlink(missing_ok=True)
            except Exception:
                pass


# ── 5. Timer ────────────────────────────────────────────────────────────────

async def test_timer() -> None:
    section("5. Timer")

    try:
        from tools.timer import set_timer, list_timers, cancel_timer, _parse_duration
    except ImportError as e:
        fail(f"import error: {e}")
        return

    # Duration parsing
    try:
        assert _parse_duration("5 minutes") == 300
        assert _parse_duration("2m30s") == 150
        assert _parse_duration("90 seconds") == 90
        assert _parse_duration("1 hour") == 3600
        assert _parse_duration("1h30m") == 5400
        ok("Duration parsing: all formats correct")
    except (AssertionError, ValueError) as e:
        fail(f"Duration parsing error: {e}")

    # Set a short timer
    try:
        result = await set_timer("3 seconds", label="test_timer")
        name = result.get("name", "")
        if name == "test_timer":
            ok(f"Timer set: {result['duration_friendly']}")
        else:
            fail(f"Unexpected timer name: {name}")
    except Exception as e:
        fail(f"set_timer raised {type(e).__name__}: {e}")
        return

    # List timers
    try:
        result = await list_timers()
        if result.get("count", 0) > 0:
            ok(f"Active timers: {result['count']}")
        else:
            fail("list_timers shows 0 after setting one")
    except Exception as e:
        fail(f"list_timers raised {type(e).__name__}: {e}")

    # Cancel it
    try:
        result = await cancel_timer("test_timer")
        if result.get("cancelled") == "test_timer":
            ok("Timer cancelled successfully")
        else:
            fail(f"Cancel result: {result}")
    except Exception as e:
        fail(f"cancel_timer raised {type(e).__name__}: {e}")


# ── Main ────────────────────────────────────────────────────────────────────

async def run_all(skip_network: bool) -> int:
    print("AURIX new tools test suite")
    print("==========================")

    await test_weather(skip_network)
    await test_system_info()
    await test_web_search(skip_network)
    await test_notes()
    await test_timer()

    section("Summary")
    print(f"  Passed: {passed}")
    print(f"  Failed: {failed}")
    print()

    if failed == 0:
        print("All tests passed.")
        return 0
    print(f"{failed} test(s) failed -- see above.")
    return 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Test AURIX tools")
    parser.add_argument(
        "--skip-network", action="store_true",
        help="Skip tests that require internet (weather, web search)",
    )
    args = parser.parse_args()
    return asyncio.run(run_all(args.skip_network))


if __name__ == "__main__":
    sys.exit(main())
