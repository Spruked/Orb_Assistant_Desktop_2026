"""Inductive pattern verification - witness layer.

FROZEN INTERFACE v1.0.0-final
============================
This validation layer is OBSERVATIONAL ONLY.

Core logic MUST NOT import from this module.
Core logic MUST ONLY emit verdicts TO this layer for witnessing.

Any changes to this interface require full system validation.
"""

from pathlib import Path
from typing import Dict, List
from .validation_state import InductiveValidationCognition


class InductiveValidator:
    def __init__(self, worker_root: Path):
        self.root = worker_root
        self.vault_path = worker_root / "vault"
        self.cognition = InductiveValidationCognition(self.vault_path)

        # Historical pattern library (reference only)
        self.historical_patterns = {}

    def validate_verdict(self, verdict_package: Dict) -> Dict:
        """Witness inductive conclusions against pattern history."""
        original = verdict_package.get("verdict", {})

        # Parallel pattern check
        pattern_check = self._check_pattern_support(original)

        # Record validation
        val_id = self.cognition.record_validation(original, pattern_check)

        return {
            "original_verdict": original,
            "validation_layer": {
                "validator": "inductive",
                "validation_id": val_id,
                "historical_support": pattern_check["frequency"],
                "similar_patterns_found": pattern_check.get("similar_patterns", []),
                "alignment": pattern_check["alignment"],
                "observation_basis": pattern_check.get("count", 0),
            },
            "delivery_status": "witnessed",
        }

    def _check_pattern_support(self, verdict: Dict) -> Dict:
        """Check if pattern has historical support."""
        pattern = verdict.get("pattern", "")

        if not pattern:
            return {
                "frequency": 0,
                "alignment": "no_pattern",
                "count": 0,
                "similar_patterns": [],
            }

        # Check against internal history
        support_data = self.cognition.pattern_support.get(
            pattern, {"checks": 0, "supports": 0}
        )

        if support_data["checks"] > 0:
            freq = support_data["supports"] / support_data["checks"]
        else:
            freq = 0.0

        # Find similar patterns (simple substring match for demo)
        similar = [
            p
            for p in self.cognition.pattern_support.keys()
            if pattern in p or p in pattern and p != pattern
        ][:3]

        return {
            "frequency": freq,
            "count": support_data["checks"],
            "alignment": "supported" if freq > 0.6 else "weak_support",
            "similar_patterns": similar,
        }

    def get_status(self) -> Dict:
        return {"role": "pattern_witness", "stats": self.cognition.get_stats()}
