"""
KnowledgeClaim — FROZEN SCHEMA v1.0.

The schema is now locked. All fields are mandatory. The lifecycle
is defined: a Claim becomes an Atom when the Correspondence Substrate
assigns it a CorrespondenceVector and it passes the promotion gate.

Open questions from GAP_F — ALL RESOLVED:
  - subject/predicate/object decomposition: explicit fields, required
  - contradictions: represented as contradicts_claim_ids list + edges in vault
  - Claim -> Atom trigger: confidence floor + correspondence vector assigned
  - correspondence vector: owned by CorrespondenceSubstrate, not this object
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class KnowledgeClaim:
    """
    Semantic unit — pre-geometric, pre-correspondence.

    Fields:
      claim_id: unique identifier
      subject: what the claim is about (entity, concept, object)
      predicate: the relationship/action asserted
      object_: the target of the predicate (trailing underscore avoids builtin shadow)
      claim_text: the full natural language statement (preserves raw meaning)
      evidence_ids: references to EvidenceItems that support this claim
      provenance: source system/person/beam that produced this claim
      timestamp: when this claim was created
      confidence: aggregate confidence from evidence (0-1)
      degradation_signal: aggregate degradation from evidence (0-1)
      contradicts_claim_ids: list of claim_ids this claim contradicts
      caveats: list of qualifying conditions or limitations
    """
    claim_id: str
    subject: str
    predicate: str
    object_: str
    claim_text: str
    evidence_ids: List[str]
    provenance: str
    timestamp: datetime
    confidence: float
    degradation_signal: float
    contradicts_claim_ids: List[str] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0,1], got {self.confidence}")
        if not (0.0 <= self.degradation_signal <= 1.0):
            raise ValueError(f"degradation_signal must be in [0,1], got {self.degradation_signal}")
        if not self.claim_id:
            raise ValueError("claim_id must be non-empty")
        if not self.claim_text:
            raise ValueError("claim_text must be non-empty")
        if not self.subject or not self.predicate:
            raise ValueError("subject and predicate must be non-empty")

    def promote_to_atom(self, correspondence_vector, atom_id: str):
        """
        Claim -> Atom transition.

        RESOLVED (GAP_A, GAP_F): Promotion requires:
          1. A CorrespondenceVector (computed by CorrespondenceSubstrate)
          2. confidence >= PROMOTION_CONFIDENCE_FLOOR (0.25)
          3. The claim has at least one evidence item
          4. A unique atom_id is provided

        Returns a KnowledgeAtom. Raises ValueError if promotion criteria not met.
        """
        from .atoms import KnowledgeAtom

        PROMOTION_CONFIDENCE_FLOOR = 0.25  # Phase 1 empirical target

        if self.confidence < PROMOTION_CONFIDENCE_FLOOR:
            raise ValueError(
                f"Claim {self.claim_id} confidence {self.confidence:.3f} below "
                f"promotion floor {PROMOTION_CONFIDENCE_FLOOR}"
            )
        if not self.evidence_ids:
            raise ValueError(f"Claim {self.claim_id} has no evidence — cannot promote")

        return KnowledgeAtom(
            atom_id=atom_id,
            observation=self.claim_text,
            correspondence_vector=correspondence_vector,
            confidence=self.confidence,
            provenance=self.provenance,
            timestamp=self.timestamp,
            source_claim_id=self.claim_id,
            evidence_ids=self.evidence_ids,
        )
