from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List


@dataclass
class OrbContributionMetrics:
    orb_id: str
    lane: str
    orb_class: str
    novelty: float = 0.0
    confidence: float = 0.0
    coverage: float = 0.0
    depth: float = 0.0
    primary_sources: int = 0
    processing_time: float = 0.0


def create_metrics_from_finding(
    orb_id: str, lane: str, orb_class: str, finding: Dict[str, Any]
) -> OrbContributionMetrics:
    payload = finding or {}
    return OrbContributionMetrics(
        orb_id=orb_id,
        lane=lane,
        orb_class=orb_class,
        novelty=float(payload.get("novelty", 0.0) or 0.0),
        confidence=float(payload.get("confidence", 0.0) or 0.0),
        coverage=float(payload.get("coverage", 0.0) or 0.0),
        depth=float(payload.get("depth", 0.0) or 0.0),
        primary_sources=int(payload.get("primary_sources", 0) or 0),
        processing_time=float(payload.get("processing_time", 0.0) or 0.0),
    )


class EPIC:
    """Minimal Epistemic Gain score calculator."""

    def __init__(self, mission_context: Dict[str, Any]):
        self.mission_context = mission_context or {}
        self.all_contributions: List[OrbContributionMetrics] = []

    def calculate_egq(self) -> float:
        if not self.all_contributions:
            return 0.0

        total = 0.0
        for item in self.all_contributions:
            score = (
                item.novelty * 0.25
                + item.confidence * 0.30
                + item.coverage * 0.20
                + item.depth * 0.20
                + min(1.0, item.primary_sources / 5.0) * 0.05
            )
            total += score
        return total / len(self.all_contributions)

