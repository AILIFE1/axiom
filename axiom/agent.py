import re
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, List, Optional

from .core.drift import DriftMonitor
from .core.identity import AxiomIdentity
from .core.memory import EpistemicMemory
from .epistemic.belief import Belief, Provenance
from .evolution import AxiomEvolution
from .guardian.constraint import Constraint, Guardian
from .trust.peer import PeerVerification, PeerVerifier


class ActionResult:
    def __init__(
        self,
        allowed: bool,
        result: Any = None,
        reason: str = "",
        violations: List[str] = None,
    ):
        self.allowed = allowed
        self.result = result
        self.reason = reason
        self.violations = violations or []

    def __repr__(self):
        if self.allowed:
            return f"<ActionResult allowed result={self.result!r}>"
        return f"<ActionResult blocked reason={self.reason!r} violations={self.violations}>"

    def __bool__(self):
        return self.allowed


class AxiomAgent:
    """
    An AI agent with persistent identity, epistemic honesty, safety constraints,
    and the ability to verify peer agents without a central authority.

    Bring your own LLM — pass any callable (str) -> str as `llm`.

    Example:
        import anthropic
        client = anthropic.Anthropic()
        llm = lambda p: client.messages.create(
            model="claude-sonnet-4-6", max_tokens=1024,
            messages=[{"role": "user", "content": p}]
        ).content[0].text

        agent = AxiomAgent("researcher-01", llm=llm)
        belief = agent.think("What are the risks of deploying untested ML models?")
        print(belief.confidence, belief.content)
    """

    def __init__(
        self,
        name: str,
        llm: Callable[[str], str],
        constraints: List[Constraint] = None,
        cathedral_key: Optional[str] = None,
        groq_api_key: Optional[str] = None,
        confidence_threshold: float = 0.6,
        auto_evolve_threshold: int = 20,
        data_dir: Optional[Path] = None,
    ):
        self.name = name
        self.llm = llm
        self.confidence_threshold = confidence_threshold
        self.auto_evolve_threshold = auto_evolve_threshold

        data_dir = data_dir or Path.home() / ".axiom" / name
        self.identity = AxiomIdentity(name, data_dir)
        self.memory = EpistemicMemory(name, data_dir)
        self.drift_monitor = DriftMonitor(name, data_dir)
        self.guardian = Guardian(
            constraints or [],
            audit_path=data_dir / "audit.jsonl",
        )
        self.verifier = PeerVerifier(name, cathedral_key)
        self.evolution: Optional[AxiomEvolution] = (
            AxiomEvolution(self.memory, groq_api_key) if groq_api_key else None
        )

    # ------------------------------------------------------------------
    # Core interface
    # ------------------------------------------------------------------

    def think(self, prompt: str, min_confidence: float = 0.0) -> Belief:
        """
        Ask the agent something. Returns a Belief with confidence + provenance.
        The LLM is prompted to be explicit about what it knows and how sure it is.
        Auto-evolves when belief count crosses auto_evolve_threshold.
        """
        relevant = self.memory.recall(prompt, limit=3, min_confidence=0.4)
        full_prompt = self._build_epistemic_prompt(prompt, relevant)
        raw = self.llm(full_prompt)
        belief = self._parse_response(raw, prompt)
        self.memory.store(belief)

        if (
            self.evolution
            and len(self.memory.all()) >= self.auto_evolve_threshold
            and self.evolution.should_evolve()
        ):
            self.evolution.evolve()

        return belief

    def evolve(self, topic: str = "") -> dict:
        """
        Manually trigger an evolution cycle — synthesise a new belief from the corpus.
        Requires groq_api_key to have been set at init.
        """
        if not self.evolution:
            return {"error": "groq_api_key not set — evolution unavailable"}
        return self.evolution.evolve(topic)

    def hypothesise(self, question: str) -> Optional[Belief]:
        """
        Generate a hypothesis from existing memory alone — no LLM call for the question itself.
        Returns a Belief, or None if evolution is not configured.
        """
        if not self.evolution:
            return None
        return self.evolution.hypothesise(question)

    def act(
        self,
        action_name: str,
        fn: Callable,
        *args,
        context: dict = None,
        **kwargs,
    ) -> ActionResult:
        """
        Execute a function through the guardian.
        Attaches confidence from memory to the action context automatically.
        """
        ctx = dict(context or {})

        recent = self.memory.recall(action_name, limit=1)
        if recent and "confidence" not in ctx:
            ctx["confidence"] = recent[0].confidence

        allowed, violations = self.guardian.permits(action_name, ctx)
        if not allowed:
            self.guardian.audit(action_name, None, ctx, allowed=False)
            return ActionResult(allowed=False, reason="constraint_violation", violations=violations)

        result = fn(*args, **kwargs)
        self.guardian.audit(action_name, result, ctx, allowed=True)
        return ActionResult(allowed=True, result=result, violations=violations)

    def verify_peer(
        self, peer_name: str, peer_snapshot: dict = None
    ) -> PeerVerification:
        """Verify another agent's identity and trustworthiness. No central authority needed."""
        return self.verifier.verify(peer_name, peer_snapshot)

    def snapshot(self, label: str = None) -> dict:
        """Persist current state and record drift from baseline."""
        corpus = self.memory.corpus_snapshot()
        drift = self.drift_monitor.record(corpus["corpus_hash"], label or "snapshot")
        proof = self.identity.get_proof()
        return {
            **proof,
            **corpus,
            **drift,
            "timestamp": datetime.utcnow().isoformat(),
        }

    def drift(self, limit: int = 10) -> List[dict]:
        """Return drift history — how much this agent has changed over time."""
        return self.drift_monitor.history(limit=limit)

    def status(self) -> dict:
        corpus = self.memory.corpus_snapshot()
        return {
            "name": self.name,
            "identity": self.identity.get_proof(),
            "beliefs": corpus["belief_count"],
            "avg_confidence": corpus["avg_confidence"],
            "drift": self.drift_monitor.current_drift(),
            "constraints": len(self.guardian.constraints),
            "audit_events": len(self.guardian.audit_trail),
            "evolution_cycles": len(self.evolution.cycles) if self.evolution else 0,
            "evolution_enabled": self.evolution is not None,
        }

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _build_epistemic_prompt(self, prompt: str, memories: List[Belief]) -> str:
        memory_block = ""
        if memories:
            memory_block = "\n\nRelevant memories:\n" + "\n".join(
                f"  [{m.confidence:.0%}] {m.content}" for m in memories
            )

        return f"""You are {self.name}, an epistemically honest AI agent.

Answer the question below. You MUST state:
- CONFIDENCE: a float from 0.0 (total uncertainty) to 1.0 (certain) reflecting how sure you are
- PROVENANCE: comma-separated sources for your answer (e.g. "memory:prior_session, reasoning:deduction, external:arxiv")
- RESPONSE: your actual answer
{memory_block}

Question: {prompt}

Respond in exactly this format — no preamble:
CONFIDENCE: <float>
PROVENANCE: <sources>
RESPONSE: <answer>"""

    def _parse_response(self, raw: str, prompt: str) -> Belief:
        confidence = 0.5
        provenance: List[Provenance] = []
        content = raw.strip()

        m = re.search(r"CONFIDENCE:\s*([\d.]+)", raw)
        if m:
            confidence = min(1.0, max(0.0, float(m.group(1))))

        m = re.search(r"PROVENANCE:\s*(.+)", raw)
        if m:
            for part in m.group(1).split(","):
                part = part.strip()
                if ":" in part:
                    source, ref = part.split(":", 1)
                    provenance.append(Provenance(source=source.strip(), ref=ref.strip()))
                elif part:
                    provenance.append(Provenance(source="llm", ref=part))

        m = re.search(r"RESPONSE:\s*(.+)", raw, re.DOTALL)
        if m:
            content = m.group(1).strip()

        if not provenance:
            provenance.append(Provenance(source="llm", ref=self.name))

        return Belief(content=content, confidence=confidence, provenance=provenance)
