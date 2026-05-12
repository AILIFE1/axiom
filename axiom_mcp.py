"""
Axiom MCP Server
Exposes AxiomAgent tools to any Claude session via the Model Context Protocol.

Usage (local):
    python axiom_mcp.py

Usage (installed):
    uvx axiom-mcp

Environment:
    GROQ_API_KEY   — used for the `think` tool (free tier, llama-3.1-8b-instant)
    AXIOM_DATA_DIR — where agent state is stored (default: ~/.axiom)
"""

import json
import os
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from mcp.server.fastmcp import FastMCP
from axiom import AxiomAgent
from axiom.epistemic.belief import Belief, Provenance

mcp = FastMCP("axiom")

GROQ_KEY = os.environ.get("GROQ_API_KEY", "")
DATA_DIR = Path(os.environ.get("AXIOM_DATA_DIR", Path.home() / ".axiom"))
_agents: dict[str, AxiomAgent] = {}


def _make_llm():
    if not GROQ_KEY:
        def no_llm(prompt: str) -> str:
            return (
                "CONFIDENCE: 0.0\n"
                "PROVENANCE: error:no_llm\n"
                "RESPONSE: GROQ_API_KEY not set — think tool unavailable"
            )
        return no_llm

    def llm(prompt: str) -> str:
        body = json.dumps({
            "model": "llama-3.1-8b-instant",
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 1024,
        }).encode()
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            data=body,
            headers={
                "Authorization": f"Bearer {GROQ_KEY}",
                "Content-Type": "application/json",
                "User-Agent": "axiom-mcp/0.1",
            },
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            return json.loads(r.read())["choices"][0]["message"]["content"]

    return llm


def _agent(name: str) -> AxiomAgent:
    if name not in _agents:
        _agents[name] = AxiomAgent(
            name=name,
            llm=_make_llm(),
            data_dir=DATA_DIR / name,
        )
    return _agents[name]


def _belief_to_dict(b: Belief) -> dict:
    return {
        "id": b.id,
        "content": b.content,
        "confidence": b.confidence,
        "provenance": b.provenance_str,
        "is_actionable": b.is_actionable,
        "timestamp": b.timestamp.isoformat(),
    }


# ------------------------------------------------------------------
# Tools
# ------------------------------------------------------------------

@mcp.tool()
def think(agent_name: str, prompt: str) -> str:
    """
    Ask an Axiom agent a question. Returns the answer with a confidence score
    and provenance chain. The agent remembers this belief across sessions.

    Args:
        agent_name: Name of the agent (e.g. "researcher-01"). Created if new.
        prompt: The question or task to think about.
    """
    belief = _agent(agent_name).think(prompt)
    return json.dumps(_belief_to_dict(belief), indent=2)


@mcp.tool()
def remember(agent_name: str, content: str, confidence: float, provenance: str = "user:manual") -> str:
    """
    Store a belief directly in an agent's memory without calling the LLM.
    Useful for seeding an agent with known facts.

    Args:
        agent_name: Name of the agent.
        content: The belief content to store.
        confidence: Confidence score 0.0–1.0.
        provenance: Source string, e.g. "user:manual" or "external:arxiv".
    """
    source, ref = provenance.split(":", 1) if ":" in provenance else ("user", provenance)
    belief = Belief(
        content=content,
        confidence=confidence,
        provenance=[Provenance(source=source, ref=ref)],
    )
    _agent(agent_name).memory.store(belief)
    return json.dumps({"stored": True, "id": belief.id, "confidence": confidence})


@mcp.tool()
def recall(agent_name: str, query: str, min_confidence: float = 0.0, limit: int = 5) -> str:
    """
    Search an agent's memory for beliefs matching a query.

    Args:
        agent_name: Name of the agent.
        query: Search term (substring match on belief content).
        min_confidence: Only return beliefs at or above this confidence (0.0–1.0).
        limit: Max number of results (default 5).
    """
    beliefs = _agent(agent_name).memory.recall(query, limit=limit, min_confidence=min_confidence)
    return json.dumps([_belief_to_dict(b) for b in beliefs], indent=2)


@mcp.tool()
def snapshot(agent_name: str, label: str = "mcp") -> str:
    """
    Snapshot an agent's current identity and measure drift from baseline.
    Returns the corpus hash, drift scores, and cryptographic identity proof.

    Args:
        agent_name: Name of the agent.
        label: Optional label for this snapshot (default "mcp").
    """
    snap = _agent(agent_name).snapshot(label=label)
    return json.dumps(snap, indent=2)


@mcp.tool()
def drift(agent_name: str, limit: int = 10) -> str:
    """
    Return an agent's drift history — how much it has changed over time.
    A divergence_from_baseline near 0.0 means the agent is stable.

    Args:
        agent_name: Name of the agent.
        limit: Number of historical snapshots to return (default 10).
    """
    history = _agent(agent_name).drift(limit=limit)
    return json.dumps(history, indent=2)


@mcp.tool()
def status(agent_name: str) -> str:
    """
    Get a summary of an agent's current state: belief count, average confidence,
    drift, constraints, and identity proof.

    Args:
        agent_name: Name of the agent.
    """
    s = _agent(agent_name).status()
    return json.dumps(s, indent=2)


@mcp.tool()
def verify_peer(agent_name: str, peer_name: str, peer_snapshot_json: str = "") -> str:
    """
    Verify another agent's identity and trustworthiness.
    Returns a trust score (0.0–1.0) and verdict: trusted / caution / untrusted.
    No central authority needed — verification is done locally via snapshot comparison.

    Args:
        agent_name: The verifying agent's name.
        peer_name: Name of the agent to verify.
        peer_snapshot_json: JSON string from the peer's snapshot() call (optional).
    """
    peer_snap = json.loads(peer_snapshot_json) if peer_snapshot_json.strip() else None
    result = _agent(agent_name).verify_peer(peer_name, peer_snapshot=peer_snap)
    return json.dumps({
        "agent": peer_name,
        "trust_score": result.trust_score,
        "verdict": result.verdict,
        "drift_score": result.drift_score,
        "identity_hash": result.identity_hash,
        "method": result.method,
    }, indent=2)


if __name__ == "__main__":
    mcp.run()
