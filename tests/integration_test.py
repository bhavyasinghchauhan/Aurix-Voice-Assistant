"""End-to-end smoke test (no audio / no LLM calls)."""
import asyncio

from core.state_manager import SystemState, SystemMode
from llm.prompt_builder import PromptBuilder
from memory.graph_memory import GraphMemory
from tools.executor import ToolExecutor


def test_full_pipeline_dry_run():
    """Wire memory + state + executor + prompt builder together without audio."""
    state = SystemState()
    state.mode = SystemMode.AI_MODE
    memory = GraphMemory()
    executor = ToolExecutor()
    builder = PromptBuilder()

    intent_id = memory.add_interaction(
        intent="open chrome",
        actions=[{"tool": "open_application", "params": {"app_name": "chrome"}}],
        result="launched",
    )
    assert intent_id

    context = memory.retrieve_context("open chrome")
    prompt = builder.build_system_prompt(
        [n.to_dict() for n in context], state.to_context_string()
    )
    assert "AURIX" in prompt
    assert state.to_context_string()

    # Executor handles unknown tool gracefully
    result = asyncio.run(
        executor.execute_tools([{"tool": "totally_fake_tool", "params": {}}])
    )
    assert result["success"] is False


if __name__ == "__main__":
    test_full_pipeline_dry_run()
    print("integration test passed")
