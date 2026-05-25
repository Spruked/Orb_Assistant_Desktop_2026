"""Deductive verification - parallel reasoning without override.

FROZEN INTERFACE v1.0.0-final
============================
This validation layer is OBSERVATIONAL ONLY.

Core logic MUST NOT import from this module.
Core logic MUST ONLY emit verdicts TO this layer for witnessing.

Any changes to this interface require full system validation.
"""

import time
from pathlib import Path
from typing import Dict, List, Tuple
from .validation_state import ValidationCognition


class DeductiveValidator:
    def __init__(self, worker_root: Path):
        self.root = worker_root
        self.vault_path = worker_root / "vault"
        self.cognition = ValidationCognition(self.vault_path)

        # Apriori truths for cross-reference (not enforcement)
        self.reference_premises = {
            "spatial_movement": {
                "attributes": ["implies_navigation", "has_velocity", "has_direction"],
                "certainty": 1.0,
            }
        }

    def validate_verdict(self, verdict_package: Dict) -> Dict:
        """
        Witness/validate a verdict before user delivery.
        Returns observation record alongside original verdict.
        """
        original = verdict_package.get("verdict", {})
        context = verdict_package.get("context", {})

        # Parallel deductive check
        check_result = self._parallel_deductive_check(original, context)

        # Document observation
        obs_id = self.cognition.record_observation(original, check_result)

        # Return validation layer info (non-blocking)
        return {
            "original_verdict": original,  # Passed through untouched
            "validation_layer": {
                "validator": "deductive",
                "observation_id": obs_id,
                "check_status": check_result["check_status"],
                "parallel_confidence": check_result["calculated_confidence"],
                "alignment": check_result["alignment"],
                "notes": check_result["reasoning_chain"],
                "timestamp": time.time(),
            },
            "delivery_status": "validated",  # Never blocked, just witnessed
        }

    def _parallel_deductive_check(self, verdict: Dict, context: Dict) -> Dict:
        """Re-reason through the logic independently."""
        v_type = verdict.get("type", "unknown")
        conclusion = verdict.get("conclusion", "")

        chain = []

        # Check against reference premises
        if v_type == "cursor_movement":
            premise = self.reference_premises.get("spatial_movement", {})
            attrs = premise.get("attributes", [])

            if "implies_navigation" in conclusion:
                chain.append("Checked: cursor_movement → navigation (premise verified)")
                calc_conf = 1.0
                status = "confirmed"
            else:
                chain.append(f"Checked: {conclusion} against spatial premises")
                calc_conf = 0.5
                status = "unverified_conclusion"
        else:
            chain.append(f"No reference premise for {v_type}")
            calc_conf = verdict.get("confidence", 0)  # Accept original
            status = "no_premise_available"

        # Calculate alignment
        orig_conf = verdict.get("confidence", 0)
        alignment = "congruent" if abs(orig_conf - calc_conf) < 0.1 else "divergent"

        return {
            "check_status": status,
            "calculated_confidence": calc_conf,
            "alignment": alignment,
            "reasoning_chain": chain,
        }

    def get_cognitive_status(self) -> Dict:
        return {
            "role": "final_validation",
            "observations_recorded": len(self.cognition.observation_log),
            "stats": self.cognition.get_validation_stats(),
        }
