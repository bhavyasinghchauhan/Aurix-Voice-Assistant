"""Core graph-based memory engine."""
import pickle
import threading
import time
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set

import networkx as nx

from memory.embeddings import Embedder, cosine_similarity
from memory.node import MemoryNode
from utils.logger import get_logger

logger = get_logger(__name__)

MAX_GRAPH_NODES = 1000
PRUNE_AGE_DAYS = 30
PRUNE_WEIGHT_THRESHOLD = 1.0


class GraphMemory:
    """
    Core graph-based memory system.
    Stores interactions as nodes, learns shortcuts, retrieves context.
    """

    def __init__(self, embedding_model: str = "all-MiniLM-L6-v2"):
        self.graph = nx.DiGraph()
        self.embedder = Embedder(embedding_model)
        self.node_index: dict[str, MemoryNode] = {}
        self._prune_lock = threading.Lock()

        # Optimization parameters
        self.max_context_nodes = 10
        self.max_traversal_depth = 3
        self.similarity_threshold = 0.7
        self.shortcut_frequency_threshold = 3

    # ─── Public API ──────────────────────────────────────────────────────────

    def add_interaction(
        self,
        intent: str,
        actions: List[dict],
        result: str,
        success: bool = True,
    ) -> str:
        """Add a complete interaction to the graph. Returns the intent node id."""
        intent_node = MemoryNode(
            type="INTENT",
            content=intent,
            embedding=self._get_embedding(intent),
            tags=self._extract_tags(intent),
        )
        self._add_node(intent_node)

        action_nodes: List[MemoryNode] = []
        for action_data in actions:
            action_node = MemoryNode(
                type="ACTION",
                content=f"{action_data.get('tool')}: {action_data.get('params', {})}",
                tags=self._extract_tags(action_data.get("tool", "")),
            )
            self._add_node(action_node)
            action_nodes.append(action_node)

        result_node = MemoryNode(
            type="RESULT",
            content=result,
            success_rate=1.0 if success else 0.0,
        )
        self._add_node(result_node)

        current = intent_node
        for action in action_nodes:
            self._add_edge(current.id, action.id, edge_type="next")
            current = action
        self._add_edge(current.id, result_node.id, edge_type="causes")

        self._detect_and_create_shortcuts(intent_node.id)

        self._maybe_prune_async()
        self.log_stats()
        return intent_node.id

    def retrieve_context(self, query: str, max_nodes: int = 10) -> List[MemoryNode]:
        """Retrieve relevant context nodes for a query."""
        t0 = time.monotonic()
        query_embedding = self._get_embedding(query)

        candidates = []
        for node in self.node_index.values():
            if node.embedding is not None:
                sim = cosine_similarity(query_embedding, node.embedding)
                if sim > self.similarity_threshold:
                    candidates.append((node, sim))

        candidates.sort(key=lambda x: x[1] * x[0].weight, reverse=True)

        context_nodes: List[MemoryNode] = []
        seen_ids: Set[str] = set()
        for node, _ in candidates[: max_nodes // 2]:
            if node.id not in seen_ids:
                seen_ids.add(node.id)
                context_nodes.append(node)
            for neighbor in self._get_neighborhood(node.id, depth=self.max_traversal_depth):
                if neighbor.id not in seen_ids:
                    seen_ids.add(neighbor.id)
                    context_nodes.append(neighbor)
            if len(context_nodes) >= max_nodes:
                break

        elapsed_ms = (time.monotonic() - t0) * 1000
        logger.debug(f"Memory retrieval: {len(context_nodes)} nodes in {elapsed_ms:.1f}ms")

        return sorted(
            context_nodes[:max_nodes],
            key=lambda n: n.timestamp,
            reverse=True,
        )

    def find_shortcut(self, query: str) -> Optional[dict]:
        """Check if a macro shortcut exists for this query."""
        query_embedding = self._get_embedding(query)

        for node in self.node_index.values():
            if node.type == "MACRO" and node.embedding is not None:
                sim = cosine_similarity(query_embedding, node.embedding)
                if sim > 0.85:
                    return {
                        "macro_id": node.id,
                        "sequence": node.compressed_sequence,
                        "confidence": sim,
                        "avg_time": node.average_execution_time,
                    }
        return None

    def clear(self) -> None:
        """Reset the graph to empty state."""
        self.graph.clear()
        self.node_index.clear()
        logger.info("Memory graph cleared")

    def log_stats(self) -> None:
        """Log current memory statistics."""
        total = len(self.node_index)
        shortcuts = sum(1 for n in self.node_index.values() if n.type == "MACRO")
        intents = sum(1 for n in self.node_index.values() if n.type == "INTENT")
        logger.info(
            f"Memory stats: {total} nodes "
            f"({intents} intents, {shortcuts} shortcuts, "
            f"{self.graph.number_of_edges()} edges)"
        )

    # ─── Pruning ────────────────────────────────────────────────────────────

    def _maybe_prune_async(self) -> None:
        """Kick off a background prune if the graph is over the size limit."""
        if len(self.node_index) > MAX_GRAPH_NODES:
            thread = threading.Thread(target=self._prune_background, daemon=True)
            thread.start()

    def _prune_background(self) -> None:
        """Run in a background thread so pruning never blocks the main loop."""
        with self._prune_lock:
            t0 = time.monotonic()
            removed = self._prune_old_low_value()
            if len(self.node_index) > MAX_GRAPH_NODES:
                removed += self._prune_to_size_limit()
            elapsed_ms = (time.monotonic() - t0) * 1000
            if removed:
                logger.info(
                    f"Background prune: removed {removed} nodes in {elapsed_ms:.1f}ms "
                    f"({len(self.node_index)} remaining)"
                )

    def _prune_old_low_value(self) -> int:
        """Remove nodes older than PRUNE_AGE_DAYS with weight below threshold."""
        cutoff = datetime.now() - timedelta(days=PRUNE_AGE_DAYS)
        to_remove = [
            nid
            for nid, node in self.node_index.items()
            if node.timestamp < cutoff
            and node.weight < PRUNE_WEIGHT_THRESHOLD
            and node.type != "MACRO"
        ]
        for nid in to_remove:
            if nid in self.graph:
                self.graph.remove_node(nid)
            self.node_index.pop(nid, None)
        return len(to_remove)

    def _prune_to_size_limit(self) -> int:
        """If still over MAX_GRAPH_NODES, drop the lowest-value non-MACRO nodes."""
        excess = len(self.node_index) - MAX_GRAPH_NODES
        if excess <= 0:
            return 0
        ranked = sorted(
            (
                (nid, node)
                for nid, node in self.node_index.items()
                if node.type != "MACRO"
            ),
            key=lambda pair: (pair[1].weight, pair[1].timestamp),
        )
        to_remove = [nid for nid, _ in ranked[:excess]]
        for nid in to_remove:
            if nid in self.graph:
                self.graph.remove_node(nid)
            self.node_index.pop(nid, None)
        return len(to_remove)

    def prune_low_value_nodes(self, min_weight: float = 0.5) -> None:
        """Remove nodes that are rarely used (manual trigger)."""
        to_remove = [
            nid
            for nid, node in self.node_index.items()
            if node.weight < min_weight and node.execution_count < 2
        ]
        for nid in to_remove:
            if nid in self.graph:
                self.graph.remove_node(nid)
            self.node_index.pop(nid, None)

    # ─── Persistence ───────────────────────────────────────────────────────

    def save(self, filepath: str) -> None:
        """Persist graph to disk."""
        data = {
            "graph": nx.to_dict_of_dicts(self.graph),
            "nodes": {nid: node.to_dict() for nid, node in self.node_index.items()},
        }
        with open(filepath, "wb") as f:
            pickle.dump(data, f)

    def load(self, filepath: str) -> None:
        """Load graph from disk."""
        with open(filepath, "rb") as f:
            data = pickle.load(f)
        self.graph = nx.from_dict_of_dicts(data["graph"], create_using=nx.DiGraph)
        self.node_index = {
            nid: MemoryNode.from_dict(node_data)
            for nid, node_data in data["nodes"].items()
        }
        self.log_stats()

    # ─── Shortcut detection ─────────────────────────────────────────────────

    def _detect_and_create_shortcuts(self, intent_id: str) -> None:
        sequence = self._get_action_sequence(intent_id)
        if not sequence:
            return
        similar_sequences = self._find_similar_sequences(sequence)
        if len(similar_sequences) >= self.shortcut_frequency_threshold:
            self._create_macro_node(sequence, similar_sequences)
            logger.info(
                f"Shortcut created: {len(similar_sequences)} similar sequences "
                f"detected for '{sequence[0][:40]}...'"
            )

    def _create_macro_node(self, sequence: List[str], instances: List[str]) -> None:
        macro_content = f"Macro: {' -> '.join(sequence[:3])}..."
        macro_node = MemoryNode(
            type="MACRO",
            content=macro_content,
            embedding=self._get_embedding(macro_content),
            compressed_sequence=sequence,
            weight=float(len(instances)),
            execution_count=len(instances),
        )
        self._add_node(macro_node)
        for instance_id in instances:
            self._add_edge(instance_id, macro_node.id, edge_type="shortcut")

    def _get_action_sequence(self, intent_id: str) -> List[str]:
        sequence: List[str] = []
        current_id = intent_id
        while current_id:
            successors = list(self.graph.successors(current_id))
            if not successors:
                break
            next_id = successors[0]
            node = self.node_index.get(next_id)
            if node and node.type == "ACTION":
                sequence.append(node.content)
                current_id = next_id
            else:
                break
        return sequence

    def _find_similar_sequences(self, target: List[str]) -> List[str]:
        similar = []
        for node in self.node_index.values():
            if node.type == "INTENT":
                seq = self._get_action_sequence(node.id)
                if self._sequences_match(target, seq, threshold=0.8):
                    similar.append(node.id)
        return similar

    @staticmethod
    def _sequences_match(seq1: List[str], seq2: List[str], threshold: float = 0.8) -> bool:
        if not seq1 or not seq2:
            return False
        s1, s2 = set(seq1), set(seq2)
        union = len(s1 | s2)
        return (len(s1 & s2) / union) >= threshold if union > 0 else False

    # ─── Graph helpers ──────────────────────────────────────────────────────

    def _get_neighborhood(self, node_id: str, depth: int = 2) -> List[MemoryNode]:
        neighbors: Set[str] = set()
        frontier: Set[str] = {node_id}
        for _ in range(depth):
            next_frontier: Set[str] = set()
            for nid in frontier:
                next_frontier.update(self.graph.successors(nid))
                next_frontier.update(self.graph.predecessors(nid))
            next_frontier -= neighbors
            neighbors.update(next_frontier)
            frontier = next_frontier
            if not frontier:
                break
        return [self.node_index[nid] for nid in neighbors if nid in self.node_index]

    def _add_node(self, node: MemoryNode) -> None:
        self.graph.add_node(node.id)
        self.node_index[node.id] = node

    def _add_edge(self, from_id: str, to_id: str, edge_type: str = "next") -> None:
        self.graph.add_edge(from_id, to_id, type=edge_type)
        if from_id in self.node_index:
            node = self.node_index[from_id]
            node.edges.setdefault(edge_type, []).append(to_id)

    def _get_embedding(self, text: str) -> List[float]:
        return self.embedder.encode(text)

    @staticmethod
    def _extract_tags(text: str) -> Set[str]:
        keywords = {"music", "youtube", "chrome", "open", "play", "search", "file", "browser"}
        return {word.lower() for word in text.split() if word.lower() in keywords}
