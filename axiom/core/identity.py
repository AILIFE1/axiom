import hashlib
import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.backends import default_backend


class AxiomIdentity:
    """Cryptographic identity for an agent. Persists across sessions."""

    def __init__(self, name: str, data_dir: Path):
        self.name = name
        self.data_dir = data_dir
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.created_at = self._load_or_set_created()
        self._key = self._load_or_generate_key()
        self._succession_log: list = []

    def _load_or_set_created(self) -> datetime:
        meta_path = self.data_dir / "identity.json"
        if meta_path.exists():
            data = json.loads(meta_path.read_text())
            return datetime.fromisoformat(data["created_at"])
        ts = datetime.utcnow()
        meta_path.write_text(json.dumps({"name": self.name, "created_at": ts.isoformat()}))
        return ts

    def _load_or_generate_key(self):
        key_path = self.data_dir / "identity.pem"
        if key_path.exists():
            return serialization.load_pem_private_key(
                key_path.read_bytes(), password=None, backend=default_backend()
            )
        key = rsa.generate_private_key(
            public_exponent=65537, key_size=2048, backend=default_backend()
        )
        key_path.write_bytes(
            key.private_bytes(
                encoding=serialization.Encoding.PEM,
                format=serialization.PrivateFormat.TraditionalOpenSSL,
                encryption_algorithm=serialization.NoEncryption(),
            )
        )
        return key

    @property
    def public_key_hex(self) -> str:
        pub = self._key.public_key()
        der = pub.public_bytes(
            serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
        )
        return hashlib.sha256(der).hexdigest()[:16]

    def sign(self, data: str) -> str:
        sig = self._key.sign(
            data.encode(),
            padding.PSS(
                mgf=padding.MGF1(hashes.SHA256()),
                salt_length=padding.PSS.MAX_LENGTH,
            ),
            hashes.SHA256(),
        )
        return sig.hex()

    def record_succession(self, predecessor: str, reason: str = "") -> dict:
        event = {
            "predecessor": predecessor,
            "successor": self.name,
            "timestamp": datetime.utcnow().isoformat(),
            "reason": reason,
            "witness_sig": self.sign(f"{predecessor}:{self.name}:{reason}"),
        }
        self._succession_log.append(event)
        return event

    def get_proof(self) -> dict:
        return {
            "name": self.name,
            "public_key": self.public_key_hex,
            "created_at": self.created_at.isoformat(),
            "successions": len(self._succession_log),
        }
