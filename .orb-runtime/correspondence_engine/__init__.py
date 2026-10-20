
"""
Correspondence Engine — AUI Engine v1.0.

The Artificial Understanding and Intelligence Engine is now complete.
All critical gaps resolved. All blockers cleared.

Pipeline:
  EvidenceItem -> SemanticSublimator -> KnowledgeClaim ->
  CorrespondenceSubstrate -> KnowledgeAtom -> Vault ->
  [HLSF/EGF via interfaces] -> Beams -> FifthMind ->
  TribunalSynthesizer -> EscalationQueue

Core AUI feature: get_understanding_window() returns the geometric
and semantic context that represents machine understanding.
"""

from .evidence import EvidenceItem
from .vectors import CorrespondenceVector
from .claims import KnowledgeClaim
from .atoms import KnowledgeAtom, CorrespondenceEdge, RelationType
from .sublimator import SemanticSublimator
from .correspondence_substrate import CorrespondenceSubstrate
from .vault import Vault
from . import geometry
from .beams import (
    HumeBeam, KantBeam, LockeBeam, SpinozaBeam,
    PhilosophicalBeam, BeamOutput, BeamVerdict,
)
from .fifth_mind import FifthMind, FifthMindOutput
from .tribunal import TribunalSynthesizer, TribunalJudgment
from .escalation import EscalationQueue, EscalationRecord
from .challenge import ReChallengeConfig, needs_rechallenge, AntifragileFeedback
from .aui_engine import AUIEngine, HLSFInterface, EGFInterface

__all__ = [
    # Primitives
    "EvidenceItem",
    "CorrespondenceVector",
    "KnowledgeClaim",
    "KnowledgeAtom",
    "CorrespondenceEdge",
    "RelationType",
    # Pipeline
    "SemanticSublimator",
    "CorrespondenceSubstrate",
    "Vault",
    "geometry",
    # Beams
    "HumeBeam",
    "KantBeam",
    "LockeBeam",
    "SpinozaBeam",
    "PhilosophicalBeam",
    "BeamOutput",
    "BeamVerdict",
    # Judgment
    "FifthMind",
    "FifthMindOutput",
    "TribunalSynthesizer",
    "TribunalJudgment",
    # Escalation
    "EscalationQueue",
    "EscalationRecord",
    # Challenge
    "ReChallengeConfig",
    "needs_rechallenge",
    "AntifragileFeedback",
    # Engine
    "AUIEngine",
    "HLSFInterface",
    "EGFInterface",
]
