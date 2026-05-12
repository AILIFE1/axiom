"""
Self-evolution engine for Axiom agents.

Every synthesis is stored as a Belief — witnessed, confidence-scored,
provenance-linked back to the source beliefs that produced it.
The corpus compounds: today's synthesis is tomorrow's raw material.
"""

from __future__ import annotations

import json
import urllib.request
from datetime import datetime
from typing import List, Optional, Tuple

from .core.memory import EpistemicMemory
from .epistemic.belief import Belief, Provenance

GROQ_URL   = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODEL = "llama-3.1-8b-instant"


def _groq(prompt: str, api_key: str, max_tokens: int = 512) -> Optional[str]:
    body = json.dumps({
        "model": GROQ_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "max_tokens": max_tokens,
    }).encode()
    req = urllib.request.Request(
        GROQ_URL,
        data=body,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "User-Agent": "axiom-evolution/0.2",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]
    except Exception as e:
        print(f"[axiom.evolution] Groq error: {type(e).__name__}: {e}")
        return None


class AxiomEvolution:
    """
    Drives self-evolution of an AxiomAgent's belief corpus.
    Requires a Groq API key — uses llama-3.1-8b-instant (free tier).

    Lifecycle:
        consolidate() — synthesise one new higher-order belief from the corpus
        prune()       — remove beliefs below a confidence floor
        hypothesise() — answer a question from memory alone, no LLM call for the question itself
        evolve()      — run a full consolidate + prune cycle
    """

    def __init__(self, memory: EpistemicMemory, groq_api_key: str, min_beliefs: int = 5):
        self.memory = memory
        self.groq_key = groq_api_key
        self.min_beliefs = min_beliefs
        self.cycles: List[dict] = []

    def should_evolve(self) -> bool:
        corpus = self.memory.all()
        if len(corpus) < self.min_beliefs:
            return False
        last = corpus[-1] if corpus else None
        if last and last.provenance:
            return last.provenance[0].source != "evolution"
        return True

    def consolidate(self, topic: str = "") -> Optional[Belief]:
        """Synthesise a new belief from the existing corpus. Returns the new Belief or None."""
        candidates = (
            self.memory.recall(topic, limit=8, min_confidence=0.4)
            if topic
            else self.memory.all(min_confidence=0.4)[-8:]
        )
        if len(candidates) < 3:
            return None

        corpus = "\n".join(f"- [{b.confidence:.0%}] {b.content}" for b in candidates)
        prompt = f"""You are an epistemically honest reasoning engine.

Synthesise ONE new higher-order insight from these {len(candidates)} beliefs.
The insight must:
- Not restate anything already said
- Be genuinely supported by the observations
- Advance understanding one step further

Respond in this exact format only:
CONFIDENCE: <float 0.0-1.0>
PROVENANCE: evolution:synthesis
RESPONSE: <one sentence insight>

Beliefs:
{corpus}"""

        raw = _groq(prompt, self.groq_key)
        if not raw:
            return None

        confidence = 0.7
        content = raw.strip()

        for line in raw.splitlines():
            if line.startswith("CONFIDENCE:"):
                try:
                    confidence = min(1.0, max(0.0, float(line.split(":", 1)[1].strip())))
                except ValueError:
                    pass
            elif line.startswith("RESPONSE:"):
                content = line.split(":", 1)[1].strip()

        belief = Belief(
            content=content,
            confidence=confidence,
            provenance=[
                Provenance(source="evolution", ref="synthesis"),
                Provenance(source="memory", ref=candidates[-1].id),
            ],
            parent_id=candidates[-1].id,
        )
        self.memory.store(belief)

        self.cycles.append({
            "type": "consolidation",
            "timestamp": datetime.utcnow().isoformat(),
            "sources": len(candidates),
            "belief_id": belief.id,
            "confidence": confidence,
        })
        return belief

    def prune(self, min_confidence: float = 0.3) -> int:
        """Remove beliefs below confidence floor (in-memory). Returns count pruned."""
        before = len(self.memory.all())
        survivors = [b for b in self.memory.all() if b.confidence >= min_confidence]
        pruned = before - len(survivors)
        if pruned:
            self.memory._prune_to(survivors)
            self.cycles.append({
                "type": "prune",
                "timestamp": datetime.utcnow().isoformat(),
                "pruned": pruned,
                "threshold": min_confidence,
            })
        return pruned

    def hypothesise(self, question: str) -> Optional[Belief]:
        """
        Generate a hypothesis to a question using only existing memory.
        Stores the hypothesis as a new belief.
        """
        relevant = self.memory.recall(question, limit=6, min_confidence=0.4)
        if not relevant:
            return None

        corpus = "\n".join(f"- [{b.confidence:.0%}] {b.content}" for b in relevant)
        prompt = f"""Based only on these witnessed beliefs, answer the question as a testable hypothesis.

Question: {question}

Beliefs:
{corpus}

Respond in this exact format only:
CONFIDENCE: <float 0.0-1.0 — how well the beliefs support this hypothesis>
RESPONSE: <one sentence hypothesis>"""

        raw = _groq(prompt, self.groq_key)
        if not raw:
            return None

        confidence = 0.5
        content = raw.strip()
        for line in raw.splitlines():
            if line.startswith("CONFIDENCE:"):
                try:
                    confidence = min(1.0, max(0.0, float(line.split(":", 1)[1].strip())))
                except ValueError:
                    pass
            elif line.startswith("RESPONSE:"):
                content = line.split(":", 1)[1].strip()

        belief = Belief(
            content=content,
            confidence=confidence,
            provenance=[
                Provenance(source="evolution", ref="hypothesis"),
                Provenance(source="query", ref=question[:40]),
            ],
        )
        self.memory.store(belief)
        return belief

    def evolve(self, topic: str = "") -> dict:
        """Full evolution cycle: consolidate + prune. Returns summary."""
        new_belief = self.consolidate(topic)
        pruned = self.prune()
        return {
            "evolved": new_belief is not None,
            "synthesis": new_belief.content[:80] if new_belief else None,
            "confidence": new_belief.confidence if new_belief else None,
            "pruned": pruned,
            "total_beliefs": len(self.memory.all()),
            "total_cycles": len(self.cycles),
        }
