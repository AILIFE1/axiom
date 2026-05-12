import sqlite3
from datetime import datetime
from pathlib import Path
from typing import List, Optional


class DriftMonitor:
    """
    Tracks how much an agent's memory corpus has changed over time.
    Uses hash-based divergence — same approach as Cathedral's /drift endpoint.
    """

    def __init__(self, agent_name: str, data_dir: Path):
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.data_dir / "drift.db"
        self._init_db()

    def _init_db(self):
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS snapshots (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    timestamp TEXT NOT NULL,
                    corpus_hash TEXT NOT NULL,
                    label TEXT,
                    divergence_from_baseline REAL NOT NULL,
                    divergence_from_previous REAL NOT NULL
                )
            """)
            conn.commit()

    def record(self, corpus_hash: str, label: str = None) -> dict:
        baseline = self._get_hash(order="ASC")
        previous = self._get_hash(order="DESC")

        div_baseline = self._divergence(baseline, corpus_hash) if baseline else 0.0
        div_previous = self._divergence(previous, corpus_hash) if previous else 0.0

        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """INSERT INTO snapshots
                   (timestamp, corpus_hash, label, divergence_from_baseline, divergence_from_previous)
                   VALUES (?,?,?,?,?)""",
                (datetime.utcnow().isoformat(), corpus_hash, label, div_baseline, div_previous),
            )
            conn.commit()

        return {
            "corpus_hash": corpus_hash,
            "label": label,
            "divergence_from_baseline": div_baseline,
            "divergence_from_previous": div_previous,
        }

    def history(self, limit: int = 10) -> List[dict]:
        with sqlite3.connect(self.db_path) as conn:
            rows = conn.execute(
                """SELECT timestamp, corpus_hash, label,
                          divergence_from_baseline, divergence_from_previous
                   FROM snapshots ORDER BY id DESC LIMIT ?""",
                (limit,),
            ).fetchall()
        return [
            {
                "timestamp": r[0],
                "corpus_hash": r[1],
                "label": r[2],
                "divergence_from_baseline": r[3],
                "divergence_from_previous": r[4],
            }
            for r in rows
        ]

    def current_drift(self) -> float:
        history = self.history(limit=1)
        return history[0]["divergence_from_baseline"] if history else 0.0

    def _get_hash(self, order: str = "ASC") -> Optional[str]:
        with sqlite3.connect(self.db_path) as conn:
            row = conn.execute(
                f"SELECT corpus_hash FROM snapshots ORDER BY id {order} LIMIT 1"
            ).fetchone()
        return row[0] if row else None

    def _divergence(self, hash_a: str, hash_b: str) -> float:
        if hash_a == hash_b:
            return 0.0
        a_bits = bin(int(hash_a, 16))[2:].zfill(len(hash_a) * 4)
        b_bits = bin(int(hash_b, 16))[2:].zfill(len(hash_b) * 4)
        diffs = sum(a != b for a, b in zip(a_bits, b_bits))
        return round(diffs / len(a_bits), 4)
