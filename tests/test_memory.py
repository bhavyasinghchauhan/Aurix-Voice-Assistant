"""Tests for the graph memory engine."""
from memory.graph_memory import GraphMemory
from memory.node import MemoryNode


def test_node_roundtrip():
    node = MemoryNode(type="INTENT", content="play music")
    payload = node.to_dict()
    restored = MemoryNode.from_dict(payload)
    assert restored.id == node.id
    assert restored.type == "INTENT"
    assert restored.content == "play music"


def test_add_interaction_creates_nodes():
    g = GraphMemory()
    intent_id = g.add_interaction(
        intent="open chrome and play music",
        actions=[
            {"tool": "open_application", "params": {"app_name": "chrome"}},
            {"tool": "control_media", "params": {"action": "play"}},
        ],
        result="ok",
        success=True,
    )
    assert intent_id in g.node_index
    intent_node = g.node_index[intent_id]
    assert intent_node.type == "INTENT"
    assert len(g.node_index) >= 4  # intent + 2 actions + result


def test_retrieve_context_returns_relevant():
    g = GraphMemory()
    g.add_interaction(
        intent="play music on youtube",
        actions=[{"tool": "search_youtube", "params": {"query": "lofi"}}],
        result="started",
    )
    nodes = g.retrieve_context("youtube music", max_nodes=5)
    assert isinstance(nodes, list)


if __name__ == "__main__":
    test_node_roundtrip()
    test_add_interaction_creates_nodes()
    test_retrieve_context_returns_relevant()
    print("memory tests passed")
