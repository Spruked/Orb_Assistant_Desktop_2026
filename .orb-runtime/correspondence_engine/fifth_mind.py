
"""
Fifth Mind — Entropy over beam verdicts ONLY (GAP_D RESOLVED).

GAP_D RESOLVED: Fifth Mind is scoped to beam-disagreement entropy only.
A SEPARATE signal, correspondence_variance, handles uncertainty across
the 5 correspondence dimensions. These are NOT overloaded.
"""

import math
from typing import Dict, List
from dataclasses import dataclass

from .beams import BeamOutput, BeamVerdict


@dataclass
class FifthMindOutput:
    entropy: float
    consensus: str
    confidence: float
    correspondence_variance: float
    recommendation: str
    reasoning: str


class FifthMind:
    def __init__(self):
        self.history: List[FifthMindOutput] = []

    def evaluate(
        self,
        beam_outputs: List[BeamOutput],
        correspondence_variance: float = 0.0,
    ) -> FifthMindOutput:
        if not beam_outputs:
            return FifthMindOutput(
                entropy=1.0,
                consensus="suspend",
                confidence=0.0,
                correspondence_variance=correspondence_variance,
                recommendation="escalate",
                reasoning="No beam outputs to evaluate"
            )

        verdict_counts: Dict[str, int] = {}
        for bo in beam_outputs:
            v = bo.verdict.value
            verdict_counts[v] = verdict_counts.get(v, 0) + 1

        total = len(beam_outputs)

        entropy = 0.0
        for count in verdict_counts.values():
            p = count / total
            if p > 0:
                entropy -= p * math.log2(p)

        normalized_entropy = entropy / 2.0 if entropy > 0 else 0.0

        max_verdict = max(verdict_counts, key=verdict_counts.get)
        max_count = verdict_counts[max_verdict]

        if max_count == total:
            consensus = max_verdict
            confidence = 1.0 - normalized_entropy
        elif max_count >= total * 0.75:
            consensus = max_verdict
            confidence = 0.7 - normalized_entropy
        elif max_count >= total * 0.5:
            consensus = max_verdict
            confidence = 0.5 - normalized_entropy
        else:
            consensus = "split"
            confidence = 0.3 - normalized_entropy

        confidence = max(0.1, confidence)

        if normalized_entropy > 0.7:
            recommendation = "escalate"
        elif normalized_entropy > 0.4:
            recommendation = "rechallenge"
        elif correspondence_variance > 0.3:
            recommendation = "rechallenge"
        else:
            recommendation = "proceed"

        reasoning = (
            f"Entropy: {normalized_entropy:.3f} over {total} beams. "
            f"Verdicts: {dict(verdict_counts)}. "
            f"Consensus: {consensus} (confidence {confidence:.3f}). "
            f"Correspondence variance: {correspondence_variance:.3f}"
        )

        output = FifthMindOutput(
            entropy=normalized_entropy,
            consensus=consensus,
            confidence=confidence,
            correspondence_variance=correspondence_variance,
            recommendation=recommendation,
            reasoning=reasoning,
        )

        self.history.append(output)
        return output

    def get_trend(self, window: int = 10) -> dict:
        recent = self.history[-window:]
        if not recent:
            return {"avg_entropy": 0.0, "trend": "stable"}

        avg = sum(o.entropy for o in recent) / len(recent)
        if len(recent) >= 2:
            first_half = sum(o.entropy for o in recent[:len(recent)//2]) / (len(recent)//2)
            second_half = sum(o.entropy for o in recent[len(recent)//2:]) / (len(recent) - len(recent)//2)
            trend = "rising" if second_half > first_half * 1.1 else \
                    "falling" if second_half < first_half * 0.9 else "stable"
        else:
            trend = "stable"

        return {
            "avg_entropy": avg,
            "trend": trend,
            "recent_evaluations": len(recent),
        }
