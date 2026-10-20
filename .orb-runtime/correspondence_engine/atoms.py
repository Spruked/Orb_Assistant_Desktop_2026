"""
KnowledgeAtom and CorrespondenceEdge — MANDATORY / FROZEN.

KnowledgeAtom = stored geometric memory object (post-sublimation,
post-correspondence-scoring). Small, immutable where practical.
Deliberately does NOT carry relationships, history, or contradictions
directly — that was the "god object" problem in an earlier draft.

CorrespondenceEdge = relational link between atoms. The graph carries
relational meaning; nodes stay lightweight.

ENHANCEMENT: Added source_claim_id and evidence_ids to KnowledgeAtom
to enable antifragile feedback loops (GAP_FEEDBACK). These fields
enable provenance tracking without bloating the atom.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import List

from .vectors import CorrespondenceVector


@dataclass(frozen=True)
class KnowledgeAtom:
    atom_id: str
    observation: str
    correspondence_vector: CorrespondenceVector
    confidence: float
    provenance: str
    timestamp: datetime
    source_claim_id: str = ""          # NEW: links back to originating claim
    evidence_ids: List[str] = None     # NEW: links back to supporting evidence
    probationary: bool = True          # NEW: GAP_PROBATION — starts True, cleared after validation
    cycles_survived: int = 0           # NEW: GAP_PROBATION — survival counter

    def __post_init__(self):
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0,1], got {self.confidence}")
        if not self.atom_id:
            raise ValueError("atom_id must be non-empty")
        if not self.observation:
            raise ValueError("observation must be non-empty")
        if self.evidence_ids is None:
            object.__setattr__(self, 'evidence_ids', [])

    def is_fully_validated(self, min_cycles: int = 3) -> bool:
        """GAP_PROBATION: Atom is no longer probationary after surviving N cycles."""
        return self.cycles_survived >= min_cycles and not self.probationary


class RelationType(Enum):
    """
    Enum, not a free string. An earlier draft used `relation: str`,
    which invites silent typo-driven failures in whatever logic
    branches on it downstream (re-challenge triggers, drift detection).
    """
    CORROBORATES = "corroborates"
    CONTRADICTS = "contradicts"
    SUPERSEDES = "supersedes"
    DRIFTS_FROM = "drifts_from"
    DEPENDS_ON = "depends_on"


@dataclass(frozen=True)
class CorrespondenceEdge:
    source_atom_id: str
    target_atom_id: str
    relation: RelationType
    weight: float
    confidence: float
    timestamp: datetime

    def __post_init__(self):
        if not (0.0 <= self.weight <= 1.0):
            raise ValueError(f"weight must be in [0,1], got {self.weight}")
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0,1], got {self.confidence}")
        if self.source_atom_id == self.target_atom_id:
            raise ValueError("an edge cannot connect an atom to itself")
