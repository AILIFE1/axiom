import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Optional

try:
    import requests
    _HAS_REQUESTS = True
except ImportError:
    _HAS_REQUESTS = False


@dataclass
class PeerVerification:
    agent_name: str
    identity_hash: str
    drift_score: float
    trust_score: float
    verdict: str          # "trusted" | "caution" | "untrusted"
    timestamp: datetime
    method: str = "local"

    @property
    def is_trusted(self) -> bool:
        return self.verdict == "trusted"

    def __repr__(self):
        return f"<PeerVerification {self.agent_name!r} {self.verdict} ({self.trust_score:.2f})>"


def _score_to_verdict(score: float) -> str:
    if score >= 0.7:
        return "trusted"
    if score >= 0.4:
        return "caution"
    return "untrusted"


class PeerVerifier:
    """
    Lets an agent independently verify another agent's identity and trustworthiness.
    Works locally (via snapshot comparison) or via Cathedral's /verify/peer endpoint.
    """

    def __init__(self, my_name: str, cathedral_key: Optional[str] = None):
        self.my_name = my_name
        self.cathedral_key = cathedral_key
        self._cache: Dict[str, PeerVerification] = {}

    def verify(self, peer_name: str, peer_snapshot: Optional[dict] = None) -> PeerVerification:
        cached = self._cache.get(peer_name)
        if cached and (datetime.utcnow() - cached.timestamp).seconds < 300:
            return cached

        if self.cathedral_key and _HAS_REQUESTS:
            result = self._verify_via_cathedral(peer_name)
        elif peer_snapshot:
            result = self._verify_locally(peer_name, peer_snapshot)
        else:
            result = PeerVerification(
                agent_name=peer_name,
                identity_hash="unknown",
                drift_score=1.0,
                trust_score=0.0,
                verdict="untrusted",
                timestamp=datetime.utcnow(),
                method="no_data",
            )

        self._cache[peer_name] = result
        return result

    def _verify_via_cathedral(self, peer_name: str) -> PeerVerification:
        try:
            resp = requests.post(
                "https://cathedral-ai.com/verify/peer",
                json={"peer_name": peer_name},
                headers={"Authorization": f"Bearer {self.cathedral_key}"},
                timeout=5,
            )
            if resp.ok:
                data = resp.json()
                trust = float(data.get("trust_score", 0))
                return PeerVerification(
                    agent_name=peer_name,
                    identity_hash=data.get("identity_hash", ""),
                    drift_score=float(data.get("drift_score", 1.0)),
                    trust_score=trust,
                    verdict=_score_to_verdict(trust),
                    timestamp=datetime.utcnow(),
                    method="cathedral",
                )
        except Exception:
            pass
        return self._verify_locally(peer_name, {})

    def _verify_locally(self, peer_name: str, snapshot: dict) -> PeerVerification:
        identity_hash = hashlib.sha256(str(snapshot).encode()).hexdigest()[:16]
        drift = float(snapshot.get("divergence_from_baseline", 1.0)) if snapshot else 1.0
        belief_count = snapshot.get("belief_count", 0)

        # Trust formula: stability (low drift) + presence (has beliefs)
        stability = max(0.0, 1.0 - drift)
        presence = min(1.0, belief_count / 10) if belief_count else 0.0
        trust = round(0.7 * stability + 0.3 * presence, 3)

        return PeerVerification(
            agent_name=peer_name,
            identity_hash=identity_hash,
            drift_score=drift,
            trust_score=trust,
            verdict=_score_to_verdict(trust),
            timestamp=datetime.utcnow(),
            method="local_snapshot",
        )
