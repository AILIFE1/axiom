import hashlib
import json
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from ..epistemic.belief import Belief, Provenance


class EpistemicMemory:
    """SQLite-backed memory where every stored belief carries confidence + provenance."""

    def __init__(self, agent_name: str, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "memory.db"
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS beliefs (
                    id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    provenance TEXT NOT NULL,
                    parent_id TEXT,
                    timestamp TEXT NOT NULL
                )
            """)
            conn.commit()

    def store(self, belief: Belief) -> str:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO beliefs VALUES (?,?,?,?,?,?)",
                (
                    belief.id,
                    belief.content,
                    belief.confidence,
                    json.dumps([{"source": p.source, "ref": p.ref} for p in belief.provenance]),
                    belief.parent_id,
                    belief.timestamp.isoformat(),
                ),
            )
            conn.commit()
        return belief.id

    def recall(self, query: str, limit: int = 5, min_confidence: float = 0.0) -> List[Belief]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT * FROM beliefs
                   WHERE content LIKE ? AND confidence >= ?
                   ORDER BY confidence DESC, timestamp DESC
                   LIMIT ?""",
                (f"%{query}%", min_confidence, limit),
            ).fetchall()
        return [self._row_to_belief(r) for r in rows]

    def all(self, min_confidence: float = 0.0) -> List[Belief]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT * FROM beliefs WHERE confidence >= ? ORDER BY timestamp DESC",
                (min_confidence,),
            ).fetchall()
        return [self._row_to_belief(r) for r in rows]

    def corpus_snapshot(self) -> dict:
        with sqlite3.connect(self.db_path) as conn:
            count = conn.execute("SELECT COUNT(*) FROM beliefs").fetchone()[0]
            avg_conf = conn.execute("SELECT AVG(confidence) FROM beliefs").fetchone()[0] or 0.0
        return {
            "belief_count": count,
            "avg_confidence": round(avg_conf, 3),
            "corpus_hash": self._corpus_hash(),
        }

    def _prune_to(self, survivors: List[Belief]):
        """Replace stored beliefs with a filtered list (used by evolution engine)."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM beliefs")
            for b in survivors:
                conn.execute(
                    "INSERT INTO beliefs VALUES (?,?,?,?,?,?)",
                    (
                        b.id, b.content, b.confidence,
                        json.dumps([{"source": p.source, "ref": p.ref} for p in b.provenance]),
                        b.parent_id, b.timestamp.isoformat(),
                    ),
                )
            conn.commit()

    def _corpus_hash(self) -> str:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                "SELECT id, content, confidence FROM beliefs ORDER BY id"
            ).fetchall()
        raw = "|".join(f"{r[0]}:{r[1]}:{r[2]}" for r in rows)
        return hashlib.sha256(raw.encode()).hexdigest()[:16]

    def _row_to_belief(self, row) -> Belief:
        prov_data = json.loads(row[3])
        provenance = [Provenance(source=p["source"], ref=p["ref"]) for p in prov_data]
        return Belief(
            id=row[0],
            content=row[1],
            confidence=row[2],
            provenance=provenance,
            parent_id=row[4],
            timestamp=datetime.fromisoformat(row[5]),
        )
