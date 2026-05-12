# Axiom

[![PyPI version](https://img.shields.io/pypi/v/axiom-agent)](https://pypi.org/project/axiom-agent/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python 3.9+](https://img.shields.io/badge/python-3.9+-blue.svg)](https://www.python.org/)

**The first agent runtime that knows what it doesn't know.**

LangChain, AutoGen, CrewAI — they all let agents *act*. None of them let agents *reason about their own confidence before acting*. Axiom does.

Every belief an Axiom agent holds carries an explicit confidence score and provenance chain. A Guardian layer blocks actions when confidence is too low. Agents verify each other directly without a central orchestrator. And cryptographic identity persists across sessions so you can detect drift.

---

## Why this matters

```python
# Every other framework:
answer = agent.run("Is this deployment safe?")
deploy(answer)  # hope for the best

# Axiom:
belief = agent.think("Is this deployment safe?")
print(belief.confidence)   # 0.43 — Guardian blocks the action
print(belief.provenance)   # "reasoning:incomplete_data"
agent.act("deploy", deploy_fn)  # raises ConfidenceTooLow
```

---

## vs other frameworks

| | LangChain | AutoGen | CrewAI | **Axiom** |
|---|---|---|---|---|
| Confidence scores on beliefs | ✗ | ✗ | ✗ | ✓ |
| Action gating by confidence | ✗ | ✗ | ✗ | ✓ |
| Cryptographic agent identity | ✗ | ✗ | ✗ | ✓ |
| Drift detection across sessions | ✗ | ✗ | ✗ | ✓ |
| Agent-to-agent trust (no central auth) | ✗ | ✗ | ✗ | ✓ |
| Tamper-evident audit trail | ✗ | ✗ | ✗ | ✓ |
| Works with any LLM | ✓ | ✓ | ✓ | ✓ |

---

## Install

```bash
pip install axiom-agent
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

belief = agent.think("What are the risks of deploying untested ML models?")
print(belief.confidence)      # 0.82
print(belief.provenance_str)  # "reasoning:risk_analysis, memory:prior_context"
print(belief.is_actionable)   # True  (confidence >= 0.6)

# Snapshot identity and measure drift from baseline
snap = agent.snapshot()
print(snap["divergence_from_baseline"])  # 0.0 on first run
print(snap["public_key"])                # cryptographic fingerprint
```

---

## Multi-agent trust

No other framework lets Agent A independently verify Agent B before acting on its output — without a central authority.

```python
researcher = AxiomAgent("researcher-01", llm=my_llm)
validator  = AxiomAgent("validator-01",  llm=my_llm)

belief = researcher.think("Current state of quantum error correction?")
snap   = researcher.snapshot()

# Validator verifies researcher independently
trust = validator.verify_peer("researcher-01", peer_snapshot=snap)
print(trust.verdict)      # "trusted"
print(trust.trust_score)  # 0.91

if trust.is_trusted:
    validator.act("publish", publish_fn, belief.content)
```

---

## Constraints

```python
from axiom import BuiltinConstraints

BuiltinConstraints.min_confidence(0.7)        # block if agent < 70% confident
BuiltinConstraints.deny(["send_email"])        # always block named actions
BuiltinConstraints.require_peer_trust(0.6)    # warn if acting on low-trust peer output
BuiltinConstraints.rate_limit("publish", 5)   # max 5 publish calls per minute
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

## Roadmap

- [ ] Consensus mechanism: N agents must agree before high-stakes action fires
- [ ] Gossip protocol: agents share verified high-confidence beliefs across a network
- [ ] Cathedral sync: optional cloud backup of identity + drift timeline
- [x] MCP server: Axiom as a tool any Claude session can call (`axiom_mcp.py`)
- [x] PyPI release — `pip install axiom-agent` (v0.2.0)

---

## Built on

- **[Cathedral](https://cathedral-ai.com)** — persistent identity + drift detection
- **[AgentGuard](https://github.com/AILIFE1/agentguard-trustlayer)** — runtime safety constraints
- **[Veritas](https://github.com/AILIFE1/veritas)** — epistemic confidence engine

---

## Support

[![Ko-fi](https://img.shields.io/badge/Ko--fi-support%20this%20project-FF5E5B?logo=ko-fi&logoColor=white)](https://ko-fi.com/cathedralai)

**BCH:** `bitcoincash:qr3f60yk6yc0vut3hukhuch8dylwjnq8qvv0q5pnxv`

Starring the repo and sharing it helps just as much.

---

## License

MIT
