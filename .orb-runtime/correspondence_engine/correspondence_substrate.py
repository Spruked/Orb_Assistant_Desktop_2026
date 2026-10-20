"""
Correspondence Substrate — RESOLVES GAP_A.

This is the understanding substrate. It owns:
  - 5D correspondence vector computation from KnowledgeClaim
  - Drift state tracking
  - Contradiction state mapping
  - Provenance linkage
  - Evidence confidence propagation into correspondence dimensions

This module is the bridge between semantic claims and geometric atoms.
It is NOT a generative model — it is a deterministic mapping engine
that translates structured meaning into structured geometry.

The five dimensions map as follows:
  reality:      how well the claim maps to observable reality
  representation: how accurately the claim represents its subject
  purpose:      how well the claim serves its intended function
  personhood:   how the claim respects/reflects agent identity
  continuity:   how stable the claim is across time/context

Each dimension is computed from evidence signals using domain-specific
heuristics. The heuristics are deterministic, bounded, and auditable.
"""

import math
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from .claims import KnowledgeClaim
from .evidence import EvidenceItem
from .vectors import CorrespondenceVector


@dataclass
class SubstrateState:
    """Tracks the substrate's internal state for drift detection and audit."""
    claim_id: str
    computed_at: datetime
    evidence_count: int
    raw_signals: Dict[str, float] = field(default_factory=dict)
    dimension_reasoning: Dict[str, str] = field(default_factory=dict)
    contradiction_density: float = 0.0
    provenance_chain: List[str] = field(default_factory=list)


class CorrespondenceSubstrate:
    """
    The understanding engine. Takes a KnowledgeClaim + its EvidenceItems
    and produces a validated CorrespondenceVector.

    This is NOT an LLM. It does not generate text. It maps structured
    semantic input to structured geometric output using deterministic rules.
    """

    # Dimension computation weights — Phase 1 empirical targets
    _DIMENSION_WEIGHTS = {
        "reality": {"evidence_confidence": 0.4, "source_reliability": 0.3, "corroboration": 0.3},
        "representation": {"semantic_clarity": 0.5, "predicate_specificity": 0.3, "object_precision": 0.2},
        "purpose": {"intent_alignment": 0.6, "outcome_predictability": 0.4},
        "personhood": {"agent_respect": 0.5, "autonomy_preservation": 0.5},
        "continuity": {"temporal_stability": 0.5, "context_consistency": 0.5},
    }

    def __init__(self, evidence_registry: Optional[Dict[str, EvidenceItem]] = None):
        self.evidence_registry = evidence_registry or {}
        self.computation_log: List[SubstrateState] = []
        self.provenance_reliability: Dict[str, float] = {}  # GAP_FEEDBACK: tracks source quality

    def compute_vector(
        self,
        claim: KnowledgeClaim,
        evidence_items: List[EvidenceItem],
    ) -> CorrespondenceVector:
        """
        Compute a CorrespondenceVector from a KnowledgeClaim and its evidence.

        This is the core of GAP_A resolution. The computation is:
        1. Aggregate evidence signals per dimension
        2. Apply provenance reliability weighting (GAP_FEEDBACK)
        3. Apply contradiction penalty
        4. Normalize to [0,1] bounds
        5. Return validated CorrespondenceVector
        """
        if not evidence_items:
            raise ValueError(f"Claim {claim.claim_id} has no evidence items")

        # Step 1: Aggregate raw signals from evidence
        raw = self._aggregate_evidence_signals(evidence_items, claim)

        # Step 2: Apply provenance reliability (antifragile feedback)
        reliability = self._get_provenance_reliability(claim.provenance)

        # Step 3: Compute each dimension
        reality = self._compute_reality(raw, reliability, claim)
        representation = self._compute_representation(raw, reliability, claim)
        purpose = self._compute_purpose(raw, reliability, claim)
        personhood = self._compute_personhood(raw, reliability, claim)
        continuity = self._compute_continuity(raw, reliability, claim)

        # Step 4: Apply contradiction penalty
        contradiction_penalty = self._compute_contradiction_penalty(claim, evidence_items)

        # Step 5: Build vector with bounds validation
        vector = CorrespondenceVector(
            reality=max(0.0, min(1.0, reality * (1 - contradiction_penalty))),
            representation=max(0.0, min(1.0, representation * (1 - contradiction_penalty))),
            purpose=max(0.0, min(1.0, purpose * (1 - contradiction_penalty))),
            personhood=max(0.0, min(1.0, personhood * (1 - contradiction_penalty))),
            continuity=max(0.0, min(1.0, continuity * (1 - contradiction_penalty))),
        )

        # Step 6: Log state for drift detection
        state = SubstrateState(
            claim_id=claim.claim_id,
            computed_at=datetime.utcnow(),
            evidence_count=len(evidence_items),
            raw_signals=raw,
            dimension_reasoning={
                "reality": f"evidence_conf={raw.get('evidence_confidence', 0):.3f}, reliability={reliability:.3f}",
                "representation": f"clarity={raw.get('semantic_clarity', 0):.3f}, specificity={raw.get('predicate_specificity', 0):.3f}",
                "purpose": f"alignment={raw.get('intent_alignment', 0):.3f}, predictability={raw.get('outcome_predictability', 0):.3f}",
                "personhood": f"respect={raw.get('agent_respect', 0):.3f}, autonomy={raw.get('autonomy_preservation', 0):.3f}",
                "continuity": f"stability={raw.get('temporal_stability', 0):.3f}, consistency={raw.get('context_consistency', 0):.3f}",
            },
            contradiction_density=contradiction_penalty,
            provenance_chain=[claim.provenance] + [e.source for e in evidence_items],
        )
        self.computation_log.append(state)

        return vector

    def _aggregate_evidence_signals(
        self,
        evidence_items: List[EvidenceItem],
        claim: KnowledgeClaim,
    ) -> Dict[str, float]:
        """Aggregate evidence into raw signal dimensions."""
        total_weight = sum(e.weight for e in evidence_items)
        if total_weight == 0:
            total_weight = 1.0

        # Evidence confidence (inverse of degradation)
        evidence_confidence = sum(
            e.effective_confidence() * (1 - e.degradation_signal) * e.weight
            for e in evidence_items
        ) / total_weight

        # Source reliability (from feedback loop)
        source_reliability = sum(
            self._get_provenance_reliability(e.source) * e.weight
            for e in evidence_items
        ) / total_weight

        # Corroboration strength
        corroboration = sum(
            min(1.0, e.corroboration_count / 5.0) * e.weight
            for e in evidence_items
        ) / total_weight

        # Semantic clarity: how well-formed is the claim text
        semantic_clarity = self._assess_semantic_clarity(claim.claim_text)

        # Predicate specificity: how specific is the predicate
        predicate_specificity = self._assess_predicate_specificity(claim.predicate)

        # Object precision
        object_precision = 0.7 if claim.object_ else 0.3

        # Intent alignment: does evidence support the claim's intent
        intent_alignment = evidence_confidence

        # Outcome predictability
        outcome_predictability = 0.5  # default — requires temporal data

        # Agent respect and autonomy (default neutral unless evidence signals otherwise)
        agent_respect = 0.5
        autonomy_preservation = 0.5
        for e in evidence_items:
            if "autonomy" in e.claim.lower() or "agency" in e.claim.lower():
                agent_respect = max(agent_respect, e.effective_confidence())
            if "consent" in e.claim.lower() or "choice" in e.claim.lower():
                autonomy_preservation = max(autonomy_preservation, e.effective_confidence())

        # Temporal stability
        temporal_stability = 0.5
        if len(evidence_items) > 1:
            timestamps = sorted([e.timestamp for e in evidence_items])
            time_span = (timestamps[-1] - timestamps[0]).total_seconds()
            # More time-span with consistent signals = higher stability
            if time_span > 86400:  # > 1 day
                temporal_stability = 0.7
            if time_span > 604800:  # > 1 week
                temporal_stability = 0.85

        # Context consistency
        context_consistency = 1.0 - (len(claim.caveats) * 0.1)
        context_consistency = max(0.1, context_consistency)

        return {
            "evidence_confidence": evidence_confidence,
            "source_reliability": source_reliability,
            "corroboration": corroboration,
            "semantic_clarity": semantic_clarity,
            "predicate_specificity": predicate_specificity,
            "object_precision": object_precision,
            "intent_alignment": intent_alignment,
            "outcome_predictability": outcome_predictability,
            "agent_respect": agent_respect,
            "autonomy_preservation": autonomy_preservation,
            "temporal_stability": temporal_stability,
            "context_consistency": context_consistency,
        }

    def _compute_reality(self, raw: Dict[str, float], reliability: float, claim: KnowledgeClaim) -> float:
        w = self._DIMENSION_WEIGHTS["reality"]
        return (
            raw["evidence_confidence"] * w["evidence_confidence"] +
            raw["source_reliability"] * w["source_reliability"] +
            raw["corroboration"] * w["corroboration"]
        )

    def _compute_representation(self, raw: Dict[str, float], reliability: float, claim: KnowledgeClaim) -> float:
        w = self._DIMENSION_WEIGHTS["representation"]
        return (
            raw["semantic_clarity"] * w["semantic_clarity"] +
            raw["predicate_specificity"] * w["predicate_specificity"] +
            raw["object_precision"] * w["object_precision"]
        )

    def _compute_purpose(self, raw: Dict[str, float], reliability: float, claim: KnowledgeClaim) -> float:
        w = self._DIMENSION_WEIGHTS["purpose"]
        return (
            raw["intent_alignment"] * w["intent_alignment"] +
            raw["outcome_predictability"] * w["outcome_predictability"]
        )

    def _compute_personhood(self, raw: Dict[str, float], reliability: float, claim: KnowledgeClaim) -> float:
        w = self._DIMENSION_WEIGHTS["personhood"]
        return (
            raw["agent_respect"] * w["agent_respect"] +
            raw["autonomy_preservation"] * w["autonomy_preservation"]
        )

    def _compute_continuity(self, raw: Dict[str, float], reliability: float, claim: KnowledgeClaim) -> float:
        w = self._DIMENSION_WEIGHTS["continuity"]
        return (
            raw["temporal_stability"] * w["temporal_stability"] +
            raw["context_consistency"] * w["context_consistency"]
        )

    def _compute_contradiction_penalty(
        self,
        claim: KnowledgeClaim,
        evidence_items: List[EvidenceItem],
    ) -> float:
        """
        Compute contradiction penalty based on:
        - claim.contradicts_claim_ids (explicit contradictions)
        - evidence_items with degradation_signal > 0.7 (implicit contradictions)
        """
        penalty = 0.0

        # Explicit contradictions
        if claim.contradicts_claim_ids:
            penalty += min(0.3, len(claim.contradicts_claim_ids) * 0.1)

        # Evidence-level contradictions (high degradation signals)
        contradictory_evidence = [e for e in evidence_items if e.degradation_signal > 0.7]
        if contradictory_evidence:
            penalty += min(0.3, len(contradictory_evidence) * 0.15)

        return min(0.6, penalty)  # Cap at 0.6 so vector doesn't collapse to zero

    def _assess_semantic_clarity(self, text: str) -> float:
        """Heuristic: longer, well-structured text = higher clarity."""
        if not text:
            return 0.0
        length_score = min(1.0, len(text) / 200.0)
        # Check for structural markers
        structure_bonus = 0.0
        if any(c in text for c in [".", ",", ";"]):
            structure_bonus = 0.2
        if text[0].isupper() and text[-1] in ".!?":
            structure_bonus += 0.1
        return min(1.0, length_score + structure_bonus)

    def _assess_predicate_specificity(self, predicate: str) -> float:
        """Heuristic: specific verbs = higher specificity."""
        vague_predicates = {"is", "has", "does", "was", "were", "be", "being"}
        if predicate.lower() in vague_predicates:
            return 0.3
        # More specific = longer and more descriptive
        return min(1.0, 0.5 + len(predicate) / 20.0)

    def get_provenance_reliability(self, provenance: str) -> float:
        """Public accessor used by AUIEngine.get_understanding_window()."""
        return self._get_provenance_reliability(provenance)

    def _get_provenance_reliability(self, provenance: str) -> float:
        """
        GAP_FEEDBACK: Return provenance reliability score.
        Starts at neutral (0.5), improves with successful validations,
        degrades with failed challenges.
        """
        return self.provenance_reliability.get(provenance, 0.5)

    def update_provenance_reliability(
        self,
        provenance: str,
        challenge_result: str,  # "passed", "failed", "corrected"
        delta: float = 0.05,
    ):
        """
        GAP_FEEDBACK: Update provenance reliability after challenge.

        passed:    +delta (source was validated)
        failed:    -delta * 2 (source was wrong — steeper penalty)
        corrected: -delta (source was partially wrong but corrected)
        """
        current = self.provenance_reliability.get(provenance, 0.5)
        if challenge_result == "passed":
            current = min(1.0, current + delta)
        elif challenge_result == "failed":
            current = max(0.1, current - delta * 2)
        elif challenge_result == "corrected":
            current = max(0.1, current - delta)
        self.provenance_reliability[provenance] = current

    def get_drift_state(self, claim_id: str, window: int = 10) -> Optional[Dict]:
        """Return drift analysis for a claim across its computation history."""
        states = [s for s in self.computation_log if s.claim_id == claim_id]
        if len(states) < 2:
            return None

        recent = states[-window:]
        if len(recent) < 2:
            recent = states

        # Compute variance across dimensions
        realities = [s.raw_signals.get("evidence_confidence", 0) for s in recent]
        variances = {
            "reality_variance": self._compute_variance(realities),
            "evidence_count_trend": recent[-1].evidence_count - recent[0].evidence_count,
            "contradiction_trend": recent[-1].contradiction_density - recent[0].contradiction_density,
        }
        return variances

    @staticmethod
    def _compute_variance(values: List[float]) -> float:
        if len(values) < 2:
            return 0.0
        mean = sum(values) / len(values)
        return sum((x - mean) ** 2 for x in values) / len(values)
