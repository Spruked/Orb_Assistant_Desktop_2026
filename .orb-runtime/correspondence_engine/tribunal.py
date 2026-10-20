
"""
Tribunal Synthesizer — Final judgment before ECM/escalation.
"""

from typing import List, Optional
from dataclasses import dataclass

from .beams import BeamOutput, BeamVerdict
from .fifth_mind import FifthMindOutput


@dataclass
class TribunalJudgment:
    final_verdict: str
    confidence: float
    beam_breakdown: dict
    fifth_mind_assessment: str
    action: str
    reasoning: str


class TribunalSynthesizer:
    def __init__(self):
        self.judgment_history: List[TribunalJudgment] = []

    def judge(
        self,
        beam_outputs: List[BeamOutput],
        fifth_mind: FifthMindOutput,
    ) -> TribunalJudgment:
        weights = {"Hume": 1.0, "Kant": 1.0, "Locke": 1.0, "Spinoza": 1.1}

        weighted_scores = {"affirm": 0.0, "deny": 0.0, "suspend": 0.0, "escalate": 0.0}
        beam_breakdown = {}

        for bo in beam_outputs:
            w = weights.get(bo.beam_name, 1.0)
            v = bo.verdict.value
            weighted_scores[v] += w * bo.confidence
            beam_breakdown[bo.beam_name] = {
                "verdict": v,
                "confidence": bo.confidence,
                "weight": w,
            }

        if fifth_mind.entropy > 0.6:
            weighted_scores["suspend"] += fifth_mind.entropy
            weighted_scores["escalate"] += fifth_mind.entropy * 0.5

        total_weight = sum(weighted_scores.values())
        if total_weight == 0:
            winner = "suspend"
            confidence = 0.5
        else:
            winner = max(weighted_scores, key=weighted_scores.get)
            confidence = weighted_scores[winner] / total_weight

        action_map = {
            "affirm": "accept",
            "deny": "reject",
            "suspend": "hold",
            "escalate": "escalate_to_ecm",
        }
        action = action_map.get(winner, "hold")

        if fifth_mind.recommendation == "escalate":
            action = "escalate_to_ecm"
            winner = "escalate"

        reasoning = (
            f"Tribunal: {winner} (confidence {confidence:.3f}). "
            f"Fifth Mind entropy: {fifth_mind.entropy:.3f}, "
            f"recommendation: {fifth_mind.recommendation}. "
            f"Correspondence variance: {fifth_mind.correspondence_variance:.3f}"
        )

        judgment = TribunalJudgment(
            final_verdict=winner,
            confidence=confidence,
            beam_breakdown=beam_breakdown,
            fifth_mind_assessment=fifth_mind.reasoning,
            action=action,
            reasoning=reasoning,
        )

        self.judgment_history.append(judgment)
        return judgment
