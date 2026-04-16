"""Background optimization passes for the memory graph."""
import asyncio
from datetime import datetime, timedelta

from memory.graph_memory import GraphMemory
from utils.logger import get_logger

logger = get_logger(__name__)


def decay_weights(graph: GraphMemory, decay_factor: float = 0.99) -> None:
    """Slowly decay node weights so unused memories fade."""
    for node in graph.node_index.values():
        node.weight *= decay_factor


def boost_used(graph: GraphMemory, node_id: str, amount: float = 0.1) -> None:
    """Increase a node's weight when it's accessed."""
    node = graph.node_index.get(node_id)
    if node is None:
        return
    node.weight += amount
    node.execution_count += 1


def expire_old_nodes(graph: GraphMemory, max_age_days: int = 90) -> int:
    """Drop low-value nodes older than max_age_days. Returns count removed."""
    cutoff = datetime.now() - timedelta(days=max_age_days)
    to_remove = [
        nid
        for nid, node in graph.node_index.items()
        if node.timestamp < cutoff and node.weight < 0.5 and node.execution_count < 2
    ]
    for nid in to_remove:
        graph.graph.remove_node(nid)
        del graph.node_index[nid]
    return len(to_remove)


async def background_optimizer(graph: GraphMemory, interval_seconds: int = 600) -> None:
    """Periodically prune and decay the graph in the background."""
    while True:
        try:
            decay_weights(graph)
            removed = expire_old_nodes(graph)
            if removed:
                logger.info(f"Pruned {removed} stale memory nodes")
        except Exception as e:
            logger.exception(f"Optimizer error: {e}")
        await asyncio.sleep(interval_seconds)
