"""Memory graph node data structure."""
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional, Set


@dataclass
class MemoryNode:
    """
    Represents a single node in the memory graph.

    Types:
    - INTENT: User's interpreted intention
    - ACTION: Executed tool/command
    - RESULT: Outcome of action
    - STATE: System state snapshot
    - MACRO: Compressed action sequence
    """

    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: str = ""
    content: str = ""
    embedding: Optional[List[float]] = None
    timestamp: datetime = field(default_factory=datetime.now)

    # Graph connections — edge types: 'next', 'causes', 'similar', 'part_of_macro', 'shortcut'
    edges: Dict[str, List[str]] = field(default_factory=dict)

    # Optimization metadata
    weight: float = 1.0
    execution_count: int = 0
    success_rate: float = 1.0
    tags: Set[str] = field(default_factory=set)

    # Macro-only fields
    compressed_sequence: Optional[List[str]] = None
    average_execution_time: float = 0.0

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type,
            "content": self.content,
            "embedding": self.embedding,
            "timestamp": self.timestamp.isoformat(),
            "edges": self.edges,
            "weight": self.weight,
            "execution_count": self.execution_count,
            "success_rate": self.success_rate,
            "tags": list(self.tags),
            "compressed_sequence": self.compressed_sequence,
            "average_execution_time": self.average_execution_time,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "MemoryNode":
        return cls(
            id=data["id"],
            type=data["type"],
            content=data["content"],
            embedding=data.get("embedding"),
            timestamp=datetime.fromisoformat(data["timestamp"]),
            edges=data.get("edges", {}),
            weight=data.get("weight", 1.0),
            execution_count=data.get("execution_count", 0),
            success_rate=data.get("success_rate", 1.0),
            tags=set(data.get("tags", [])),
            compressed_sequence=data.get("compressed_sequence"),
            average_execution_time=data.get("average_execution_time", 0.0),
        )
