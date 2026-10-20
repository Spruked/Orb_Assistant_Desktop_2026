
"""
Organized Doubt / re-challenge — RESOLVED with antifragile feedback loop.

GAP_FEEDBACK RESOLVED: Successful challenges now propagate corrections:
  - Correct the atom
  - Down-weight weak provenance
  - Flag bad sublimation patterns
  - Reduce future influence of similar unverified claims

GAP_PROBATION RESOLVED: New atoms start probationary with reduced influence.
"""

from dataclasses import dataclass
from typing import Dict, List, Optional

from .atoms import KnowledgeAtom, CorrespondenceEdge, RelationType
from .vault import Vault
from .correspondence_substrate import CorrespondenceSubstrate


@dataclass
class ReChallengeConfig:
    low_confidence_threshold: float = 0.35
    contradiction_edge_increase_threshold: int = 2
    neighbor_variance_threshold: float = 0.25
    max_cycles_without_revalidation: int = 500
    probation_sensitivity_multiplier: float = 2.0


def needs_rechallenge(
    atom: KnowledgeAtom,
    vault: Vault,
    config: ReChallengeConfig,
    current_cycle: int,
    atom_last_validated_cycle: int,
) -> List[str]:
    reasons = []

    effective_confidence_threshold = config.low_confidence_threshold
    if atom.probationary:
        effective_confidence_threshold *= config.probation_sensitivity_multiplier

    if atom.confidence < effective_confidence_threshold:
        reasons.append("low_confidence")

    contradiction_edges = [
        e for e in vault.edges_for(atom.atom_id)
        if e.relation == RelationType.CONTRADICTS
    ]
    effective_contradiction_threshold = config.contradiction_edge_increase_threshold
    if atom.probationary:
        effective_contradiction_threshold = 1

    if len(contradiction_edges) >= effective_contradiction_threshold:
        reasons.append("rising_contradictions")

    cycles_elapsed = current_cycle - atom_last_validated_cycle
    effective_stale_threshold = config.max_cycles_without_revalidation
    if atom.probationary:
        effective_stale_threshold = max(10, config.max_cycles_without_revalidation // 10)

    if cycles_elapsed >= effective_stale_threshold:
        reasons.append("stale_revalidation")

    neighbors = vault.get_neighbors(atom.atom_id)
    if neighbors:
        from .geometry import correspondence_variance
        variance = correspondence_variance(atom, neighbors)
        if variance > config.neighbor_variance_threshold:
            reasons.append("high_neighbor_variance")

    return reasons


class AntifragileFeedback:
    """
    GAP_FEEDBACK RESOLVED: The antifragile feedback engine.
    """

    def __init__(self, substrate: CorrespondenceSubstrate):
        self.substrate = substrate
        self.sublimation_pattern_scores: Dict[str, float] = {}
        self.correction_log: List[dict] = []

    def process_challenge_result(
        self,
        atom: KnowledgeAtom,
        vault: Vault,
        result: str,
        corrected_vector=None,
    ) -> dict:
        actions = []

        if result == "validated":
            self.substrate.update_provenance_reliability(
                atom.provenance, "passed"
            )
            actions.append(f"provenance '{atom.provenance}' reliability increased")

        elif result == "corrected":
            self.substrate.update_provenance_reliability(
                atom.provenance, "corrected"
            )
            actions.append(f"provenance '{atom.provenance}' reliability decreased (corrected)")

            if corrected_vector:
                from dataclasses import replace
                corrected_atom = replace(
                    atom,
                    correspondence_vector=corrected_vector,
                    confidence=min(atom.confidence, 0.7),
                )
                vault.atoms[atom.atom_id] = corrected_atom
                actions.append(f"atom {atom.atom_id} corrected with new vector")

        elif result == "removed":
            self.substrate.update_provenance_reliability(
                atom.provenance, "failed"
            )
            actions.append(f"provenance '{atom.provenance}' reliability decreased (failed)")

            if atom.atom_id in vault.atoms:
                del vault.atoms[atom.atom_id]
                vault.edges = [
                    e for e in vault.edges
                    if atom.atom_id not in (e.source_atom_id, e.target_atom_id)
                ]
                actions.append(f"atom {atom.atom_id} removed from vault")

        pattern_key = self._extract_pattern_key(atom.observation)
        current_score = self.sublimation_pattern_scores.get(pattern_key, 0.5)
        if result in ("corrected", "removed"):
            self.sublimation_pattern_scores[pattern_key] = max(0.1, current_score - 0.1)
            actions.append(f"sublimation pattern '{pattern_key}' flagged (score: {self.sublimation_pattern_scores[pattern_key]:.2f})")
        else:
            self.sublimation_pattern_scores[pattern_key] = min(1.0, current_score + 0.02)

        record = {
            "atom_id": atom.atom_id,
            "result": result,
            "provenance": atom.provenance,
            "actions": actions,
            "pattern_key": pattern_key,
        }
        self.correction_log.append(record)

        vault.atom_validation_cycles[atom.atom_id] = vault.cycle_count

        return record

    def _extract_pattern_key(self, observation: str) -> str:
        words = observation.lower().split()[:5]
        return "_".join(words)

    def get_pattern_risk_score(self, observation: str) -> float:
        pattern_key = self._extract_pattern_key(observation)
        return self.sublimation_pattern_scores.get(pattern_key, 0.5)

    def get_weakest_provenances(self, n: int = 5) -> List[tuple]:
        sorted_provs = sorted(
            self.substrate.provenance_reliability.items(),
            key=lambda x: x[1]
        )
        return sorted_provs[:n]
