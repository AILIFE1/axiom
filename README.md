# Axiom

**The first agent runtime with built-in epistemic honesty.**

Current AI agent frameworks give you tool use, orchestration, and sometimes memory. None of them ask: *how confident is this agent in what it's saying?* None of them let agents verify each other without a central orchestrator. None of them track whether an agent has drifted from its original identity.

Axiom fixes all three.

---

## What it gives you

| Problem | Axiom's answer |
|---|---|
| Agents hallucinate with full confidence | Every belief carries a `confidence` score (0–1) and a provenance chain |
| Sessions are stateless — agents forget who they are | Cryptographic identity persists to disk, drift-monitored across sessions |
| You can't trust another agent's output | Agents verify each other directly via snapshot comparison — no central authority |
| No audit trail when agents act | Every action passes through the Guardian, fully logged |

---

## Install

```bash
pip install axiom-agent
```

Or from source:

```bash
git clone https://github.com/AILIFE1/axiom
cd axiom
pip install -e .
```

---

## Quick start

```python
import anthropic
from axiom import AxiomAgent, BuiltinConstraints

client = anthropic.Anthropic()

def my_llm(prompt: str) -> str:
    return client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    ).content[0].text

agent = AxiomAgent(
    name="researcher-01",
    llm=my_llm,
    constraints=[BuiltinConstraints.min_confidence(0.6)],
)

# Every answer carries confidence + provenance — not just raw text
belief = agent.think("What are the risks of deploying untested ML models?")
print(belief.confidence)      # 0.82
print(belief.provenance_str)  # "reasoning:risk_analysis, memory:prior_context"
print(belief.is_actionable)   # True  (confidence >= 0.6)
print(belief.content)         # the answer

# Snapshot identity and measure drift from baseline
snap = agent.snapshot()
print(snap["divergence_from_baseline"])  # 0.0 on first run
print(snap["public_key"])                # cryptographic fingerprint
```

---

## Multi-agent trust (the new bit)

No other framework lets Agent A independently verify Agent B before acting on its output.

```python
researcher = AxiomAgent("researcher-01", llm=my_llm)
validator  = AxiomAgent("validator-01",  llm=my_llm)

# Researcher forms a belief and snapshots itself
belief = researcher.think("Current state of quantum error correction?")
snap   = researcher.snapshot()

# Validator verifies researcher independently — no central authority
trust = validator.verify_peer("researcher-01", peer_snapshot=snap)
print(trust.verdict)      # "trusted"
print(trust.trust_score)  # 0.91

# Gate an action on both the validator's confidence AND peer trust
if trust.is_trusted:
    result = validator.act(
        "publish",
        publish_fn,
        belief.content,
        context={"confidence": belief.confidence, "peer_trust": trust.trust_score},
    )
```

---

## Architecture

```
axiom/
├── agent.py              ← AxiomAgent — the main interface
├── core/
│   ├── identity.py       ← RSA-2048 cryptographic identity, persists to disk
│   ├── memory.py         ← SQLite-backed beliefs with confidence + provenance
│   └── drift.py          ← hash-based drift monitoring across snapshots
├── epistemic/
│   └── belief.py         ← Belief dataclass: content + confidence + provenance
├── guardian/
│   └── constraint.py     ← action gating + tamper-evident audit trail
└── trust/
    └── peer.py           ← agent-to-agent verification (local or Cathedral-backed)
```

---

## Built on

This repo is the synthesis of several projects:

- **[Cathedral](https://cathedral-ai.com)** — persistent identity + drift detection (the memory + snapshot model)
- **[AgentGuard](https://github.com/AILIFE1/agentguard-trustlayer)** — runtime safety constraints + audit chain
- **[Veritas](https://github.com/AILIFE1/veritas)** — epistemic confidence engine (every belief has a provenance)
- **Aether** — cryptographic succession protocol (identity handoff between agent versions)

Axiom unifies them into a single runtime anyone can wrap around any LLM.

---

## Constraints

Axiom ships with four built-in constraints. You can also write your own.

```python
from axiom import BuiltinConstraints

BuiltinConstraints.min_confidence(0.7)        # block if agent < 70% confident
BuiltinConstraints.deny(["send_email"])        # always block named actions
BuiltinConstraints.require_peer_trust(0.6)    # warn if acting on low-trust peer output
BuiltinConstraints.rate_limit("publish", 5)   # max 5 publish calls per minute
```

---

## Roadmap

- [ ] Consensus mechanism: N agents must agree before high-stakes action fires
- [ ] Gossip protocol: agents share verified high-confidence beliefs across a network
- [ ] Cathedral sync: optional cloud backup of identity + drift timeline
- [x] MCP server: Axiom as a tool any Claude session can call (`axiom_mcp.py`)
- [x] PyPI release — `pip install axiom-agent` (v0.2.0)

---

## Support

Axiom is built and maintained by one person in their spare time. If it's useful to you, a small contribution goes a long way.

[![Ko-fi](https://img.shields.io/badge/Ko--fi-support%20this%20project-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/cathedralai)

**BCH:** `bitcoincash:qr3f60yk6yc0vut3hukhuch8dylwjnq8qvv0q5pnxv`

No pressure — starring the repo and sharing it helps just as much.

---

## License

MIT
