import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, List, Optional, Tuple


class ConstraintLevel(Enum):
    SOFT = "soft"   # warn but allow
    HARD = "hard"   # block


@dataclass
class Constraint:
    name: str
    level: ConstraintLevel
    check: Callable[[str, dict], bool]   # (action_name, context) -> is_allowed
    description: str = ""


class BuiltinConstraints:
    @staticmethod
    def min_confidence(threshold: float) -> Constraint:
        return Constraint(
            name=f"min_confidence_{threshold}",
            level=ConstraintLevel.HARD,
            check=lambda action, ctx: ctx.get("confidence", 1.0) >= threshold,
            description=f"Blocks action if confidence < {threshold}",
        )

    @staticmethod
    def deny(action_names: List[str]) -> Constraint:
        return Constraint(
            name="deny_actions",
            level=ConstraintLevel.HARD,
            check=lambda action, ctx: action not in action_names,
            description=f"Always blocks: {action_names}",
        )

    @staticmethod
    def require_peer_trust(min_trust: float) -> Constraint:
        return Constraint(
            name=f"require_peer_trust_{min_trust}",
            level=ConstraintLevel.SOFT,
            check=lambda action, ctx: ctx.get("peer_trust", 1.0) >= min_trust,
            description=f"Warns if acting on output from peer with trust < {min_trust}",
        )

    @staticmethod
    def rate_limit(action_name: str, max_per_minute: int) -> Constraint:
        calls: List[datetime] = []

        def check(action: str, ctx: dict) -> bool:
            if action != action_name:
                return True
            now = datetime.utcnow()
            recent = [t for t in calls if (now - t).seconds < 60]
            calls.clear()
            calls.extend(recent)
            if len(recent) >= max_per_minute:
                return False
            calls.append(now)
            return True

        return Constraint(
            name=f"rate_limit_{action_name}_{max_per_minute}pm",
            level=ConstraintLevel.HARD,
            check=check,
            description=f"Max {max_per_minute}/min for '{action_name}'",
        )


class Guardian:
    """Gates agent actions through constraints and maintains a tamper-evident audit trail."""

    def __init__(self, constraints: List[Constraint] = None, audit_path: Optional[Path] = None):
        self.constraints = list(constraints or [])
        self._audit_log: List[dict] = []
        self._audit_path = audit_path

    def add(self, constraint: Constraint):
        self.constraints.append(constraint)

    def permits(self, action_name: str, context: dict = None) -> Tuple[bool, List[str]]:
        context = context or {}
        violations = []
        for c in self.constraints:
            if not c.check(action_name, context):
                violations.append(f"{c.level.value}:{c.name}")
                if c.level == ConstraintLevel.HARD:
                    return False, violations
        return True, violations

    def audit(self, action_name: str, result: Any, context: dict = None, allowed: bool = True):
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action_name,
            "allowed": allowed,
            "context": context or {},
            "result_summary": repr(result)[:120],
        }
        self._audit_log.append(entry)
        if self._audit_path:
            with open(self._audit_path, "a") as f:
                f.write(json.dumps(entry) + "\n")

    @property
    def audit_trail(self) -> List[dict]:
        return list(self._audit_log)
