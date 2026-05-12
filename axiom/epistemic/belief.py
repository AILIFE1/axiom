from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List
import uuid


@dataclass
class Provenance:
    source: str   # "memory", "llm", "peer", "reasoning", "external"
    ref: str      # specific reference or identifier
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __str__(self):
        return f"{self.source}:{self.ref}"


@dataclass
class Belief:
    content: str
    confidence: float = 0.5          # 0.0 – 1.0
    provenance: List[Provenance] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    parent_id: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)

    @property
    def is_actionable(self) -> bool:
        return self.confidence >= 0.6

    @property
    def provenance_str(self) -> str:
        return ", ".join(str(p) for p in self.provenance)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "content": self.content,
            "confidence": self.confidence,
            "provenance": [{"source": p.source, "ref": p.ref} for p in self.provenance],
            "parent_id": self.parent_id,
            "timestamp": self.timestamp.isoformat(),
        }

    def __repr__(self):
        return f"<Belief [{self.confidence:.0%}] {self.content[:60]!r}>"
