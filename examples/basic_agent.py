"""
Basic Axiom example — single agent, epistemic beliefs, drift snapshot.
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


agent = AxiomAgent(
    name="researcher-01",
    llm=claude,
    constraints=[
        BuiltinConstraints.min_confidence(0.6),   # block actions below 60% confidence
    ],
)

# Ask something — every answer carries confidence + provenance
belief = agent.think("What are the main risks of deploying untested ML models in production?")

print(f"Confidence:  {belief.confidence:.0%}")
print(f"Provenance:  {belief.provenance_str}")
print(f"Actionable:  {belief.is_actionable}")
print(f"\nAnswer:\n{belief.content}")

# Snapshot identity and measure drift
snap = agent.snapshot(label="first-run")
print(f"\nDrift from baseline: {snap['divergence_from_baseline']}")
print(f"Corpus hash:         {snap['corpus_hash']}")
print(f"Public key:          {snap['public_key']}")

# Check status
print(f"\nAgent status: {agent.status()}")
