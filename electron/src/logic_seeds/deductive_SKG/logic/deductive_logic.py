"""Deductive logic with verdict scoring and recursive improvement."""

from pathlib import Path
import sys
from typing import Dict, Tuple, List, Optional
from .cognitive_state import DeductiveCognition


class DeductiveEngine:
    def __init__(self, worker_root: Path):
        self.root = worker_root
        self.vault_path = worker_root / "vault"
        self.cognition = DeductiveCognition(self.vault_path)

    def modus_ponens(
        self, antecedent: str, consequent: str, antecedent_true: bool
    ) -> Tuple[bool, float, str]:
        if not antecedent_true:
            return False, 0.0, ""

        conclusion = f"{consequent} [derived from {antecedent}]"

        self.cognition.record_syllogism(
            major=f"If {antecedent} then {consequent}",
            minor=f"{antecedent} is true",
            conclusion=conclusion,
            valid=True,
            certainty=1.0,
        )

        return True, 1.0, conclusion

    def syllogistic_chain(
        self, major_cat: str, minor_inst: str, conclusion_attr: str
    ) -> Dict:
        major_premise = self.cognition.get_premise(major_cat)

        if not major_premise:
            return {
                "valid": False,
                "certainty": 0.0,
                "verdict": "major_premise_missing",
                "conclusion": "unknown",
                "chain": [],
                "ethics_alignment": 0.0,
            }

        rule = major_premise.get("rule", {})
        attributes = rule.get("attributes", [])

        conclusion_valid = conclusion_attr in attributes
        certainty = (
            1.0 * major_premise.get("reliability", 1.0) if conclusion_valid else 0.0
        )

        conclusion_str = f"{minor_inst} has {conclusion_attr}"

        chain = [
            {"type": "major", "content": f"All {major_cat} have {attributes}"},
            {"type": "minor", "content": f"{minor_inst} is {major_cat}"},
            {"type": "conclusion", "content": conclusion_str},
        ]

        self.cognition.record_syllogism(
            major=str(chain[0]),
            minor=str(chain[1]),
            conclusion=str(chain[2]),
            valid=conclusion_valid,
            certainty=certainty,
        )

        # Calculate ethics alignment
        ethics_score = 0.4 + (0.6 if conclusion_valid else 0.0)

        verdict_data = {
            "valid": conclusion_valid,
            "certainty": certainty,
            "verdict": (
                "deductive_conclusion" if conclusion_valid else "invalid_conclusion"
            ),
            "conclusion": conclusion_str,
            "chain_consistency": True,
            "ethics_alignment": ethics_score,
        }

        # Record to tracelog
        verdict_id = self.cognition.record_verdict(
            verdict_data, {"major": major_cat, "minor": minor_inst}
        )
        verdict_data["verdict_id"] = verdict_id

        return verdict_data

    def advise_orb(self, stimulus_type: str, hlsf_node_data: Dict) -> Dict:
        if stimulus_type == "cursor_movement":
            verdict = self.syllogistic_chain(
                major_cat="spatial_movement",
                minor_inst="current_stimulus",
                conclusion_attr="implies_navigation",
            )

            # Scale weight by historical accuracy
            calibration = self.cognition.confidence_calibration
            historical_weight = (
                verdict["certainty"] * calibration["confidence_accuracy"]
            )

            return {
                "advisory_type": "deductive",
                "verdict_id": verdict.get("verdict_id"),
                "verdict": verdict["verdict"],
                "conclusion": verdict["conclusion"],
                "certainty": verdict["certainty"],
                "valid": verdict["valid"],
                "ethics_alignment": verdict["ethics_alignment"],
                "deterministic": True,
                "weight": historical_weight * 0.4,
                "calibration_confidence": calibration["confidence_accuracy"],
            }

        return {
            "advisory_type": "deductive",
            "verdict_id": None,
            "verdict": "insufficient_premises",
            "certainty": 0.0,
            "weight": 0.0,
            "ethics_alignment": 0.0,
        }

    def process_idle_feedback(self) -> Dict:
        """Entry point for CALI idle-time recursive processing."""
        return self.cognition.idle_recursive_process()

    def validate_verdict(self, verdict_id: str, was_correct: bool):
        """External validation callback."""
        self.cognition.mark_verdict_used(verdict_id, was_correct)

    def get_cognitive_status(self) -> Dict:
        return {
            "validity_score": self.cognition.calculate_validity_score(),
            "premise_count": len(self.cognition.premise_base),
            "chain_depth": len(self.cognition.syllogism_chain),
            "calibration": self.cognition.get_calibration_report(),
            "recent_apriori": [
                t.statement for t in list(self.cognition.apriori_truths.values())[-5:]
            ],
        }

    def export_tracelog_for_cali(self) -> List[Dict]:
        """Provide tracelog data to CALI for meta-analysis."""
        return [
            {
                "verdict_id": t.verdict_id,
                "confidence": t.confidence,
                "was_correct": t.was_correct,
                "ethics_score": t.ethics_alignment_score,
                "verdict_type": t.verdict_type,
            }
            for t in self.cognition.verdict_tracelog
            if t.was_used  # Only exported used verdicts for pattern analysis
        ]
