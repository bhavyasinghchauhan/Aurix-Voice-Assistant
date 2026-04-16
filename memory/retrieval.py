"""High-level retrieval helpers over a GraphMemory instance."""
from typing import List

from memory.graph_memory import GraphMemory
from memory.node import MemoryNode


def retrieve_for_prompt(
    graph: GraphMemory, query: str, max_nodes: int = 5
) -> List[dict]:
    """Retrieve top context nodes formatted as plain dicts for prompt building."""
    nodes = graph.retrieve_context(query, max_nodes=max_nodes)
    return [node.to_dict() for node in nodes]


def retrieve_macros(graph: GraphMemory) -> List[MemoryNode]:
    """Return all macro nodes ordered by usage."""
    macros = [n for n in graph.node_index.values() if n.type == "MACRO"]
    return sorted(macros, key=lambda n: n.execution_count, reverse=True)


def retrieve_recent(graph: GraphMemory, limit: int = 10) -> List[MemoryNode]:
    """Return the most recent nodes by timestamp."""
    nodes = sorted(
        graph.node_index.values(), key=lambda n: n.timestamp, reverse=True
    )
    return nodes[:limit]
