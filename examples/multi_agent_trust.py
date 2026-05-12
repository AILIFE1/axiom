"""
Multi-agent trust example — two agents, peer verification, consensus before action.
This is the novel bit: Agent A verifies Agent B without any central authority.
Requires: pip install anthropic axiom-agent
"""

import anthropic
from axiom import AxiomAgent, BuiltinConstraints

client = anthropic.Anthropic()


def claude(prompt: str) -> str:
    msg = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return msg.content[0].text


# Two independent agents
researcher = AxiomAgent(
    name="researcher-01",
    llm=claude,
    constraints=[BuiltinConstraints.min_confidence(0.5)],
)

validator = AxiomAgent(
    name="validator-01",
    llm=claude,
    constraints=[
        BuiltinConstraints.min_confidence(0.7),
        BuiltinConstraints.require_peer_trust(0.6),
    ],
)

# Researcher forms a belief
topic = "What is the current scientific consensus on large language model reasoning?"
research = researcher.think(topic)
print(f"[researcher-01] ({research.confidence:.0%}) {research.content[:120]}...")

# Researcher snapshots itself — this is the proof it hands to the validator
researcher_snap = researcher.snapshot(label="after-research")

# Validator independently verifies the researcher before trusting its output
trust = validator.verify_peer("researcher-01", peer_snapshot=researcher_snap)
print(f"\n[validator-01] Peer verification of researcher-01:")
print(f"  Trust score: {trust.trust_score:.2f}  Verdict: {trust.verdict}  Method: {trust.method}")

# Validator only processes the research if the peer is trusted
if trust.is_trusted:
    validation = validator.think(
        f"Review and validate this claim (confidence {research.confidence:.0%}): {research.content}"
    )
    print(f"\n[validator-01] ({validation.confidence:.0%}) {validation.content[:120]}...")

    # Gate a downstream action on both confidence and peer trust
    def publish(finding: str):
        print(f"\n>> Publishing: {finding[:80]}...")
        return {"published": True}

    result = validator.act(
        "publish",
        publish,
        validation.content,
        context={"confidence": validation.confidence, "peer_trust": trust.trust_score},
    )
    print(f"Action result: {result}")
else:
    print(f"\n[validator-01] Refused to act — peer trust too low ({trust.trust_score:.2f})")

# Both agents snapshot their final state
print(f"\n[researcher-01] drift: {researcher.drift_monitor.current_drift():.4f}")
print(f"[validator-01]  drift: {validator.drift_monitor.current_drift():.4f}")
