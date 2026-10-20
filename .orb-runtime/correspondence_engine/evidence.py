"""
EvidenceItem — MANDATORY / FROZEN.

Carries confidence and degradation_signal as independent axes, so a
dimension score reflects what the evidence *says*, weighted by how
sure we are it's true — not confidence alone. This is the fix that
corrected v0.2's core bug (raw_score algebraically reduced to
confidence itself, with no way to encode direction).

NOTE: This is the raw evidence primitive only. The old
`score_from_evidence` / `ScoredDimension` aggregation (from the
earlier institutional-fragility "auditor" design) is deliberately
NOT reproduced here — that was the model this project moved away
from. In the current architecture, EvidenceItem feeds
SemanticSublimator, not a direct scoring function. See sublimator.py.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import List


@dataclass
class EvidenceItem:
    """
    degradation_signal in [0, 1]:
        0.0 = strong evidence of health / correspondence
        1.0 = strong evidence of degradation / loss of correspondence
        0.5 = neutral or ambiguous

    confidence in [0, 1]: how certain we are the claim is true.
    The two are independent axes. Conflating them was the v0.2 bug.
    """
    claim: str
    source: str
    confidence: float
    degradation_signal: float
    timestamp: datetime
    supports_dimension: str
    weight: float = 1.0
    corroboration_count: int = 1
    contradicts: List[str] = field(default_factory=list)
    caveats: List[str] = field(default_factory=list)

    def __post_init__(self):
        if not (0.0 <= self.confidence <= 1.0):
            raise ValueError(f"confidence must be in [0,1], got {self.confidence}")
        if not (0.0 <= self.degradation_signal <= 1.0):
            raise ValueError(f"degradation_signal must be in [0,1], got {self.degradation_signal}")
        if self.weight < 0:
            raise ValueError(f"weight must be non-negative, got {self.weight}")
        if self.corroboration_count < 1:
            raise ValueError(f"corroboration_count must be >= 1, got {self.corroboration_count}")

    def effective_confidence(self) -> float:
        """Confidence boosted by corroboration, diminishing returns, capped."""
        bonus = min(0.15, 0.05 * (self.corroboration_count - 1))
        return min(0.98, self.confidence + bonus)

    def weighted_signal(self) -> float:
        """This item's contribution: degradation_signal weighted by effective confidence."""
        return self.effective_confidence() * self.degradation_signal

    def summary(self) -> str:
        direction = "DEGRADED" if self.degradation_signal >= 0.7 else (
            "HEALTHY" if self.degradation_signal <= 0.3 else "NEUTRAL"
        )
        return (
            f"[{self.supports_dimension}] {self.claim[:80]} "
            f"(signal={self.degradation_signal:.2f} {direction}, "
            f"conf={self.effective_confidence():.2f}, "
            f"src={self.source[:30]}, corr={self.corroboration_count})"
        )
