"""Tests for the tool execution layer."""
import asyncio

from tools.executor import ToolExecutor
from utils.error_handler import ToolExecutionError


def test_executor_unknown_tool():
    executor = ToolExecutor()
    result = asyncio.run(
        executor.execute_tools([{"tool": "does_not_exist", "params": {}}])
    )
    assert result["success"] is False
    assert result["results"][0]["success"] is False


def test_executor_handles_empty_list():
    executor = ToolExecutor()
    result = asyncio.run(executor.execute_tools([]))
    assert result["success"] is True
    assert result["results"] == []


def test_file_search_returns_dict():
    from tools.file_system import file_search

    out = asyncio.run(file_search("nonexistent_file_xyz_12345"))
    assert "matches" in out


if __name__ == "__main__":
    test_executor_unknown_tool()
    test_executor_handles_empty_list()
    test_file_search_returns_dict()
    print("tools tests passed")
