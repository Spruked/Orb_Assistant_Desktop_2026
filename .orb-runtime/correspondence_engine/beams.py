
"""
TPC Beam Interface — with circularity guard (GAP_C RESOLVED).

Beams consume geometrically-placed KnowledgeAtoms and produce
verdicts. They do NOT produce evidence directly.

GAP_C RESOLVED INVARIANT:
  A beam may not reinforce its own newly produced atom until that
  atom passes independent validation or probation.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Set
from dataclasses import dataclass
from enum import Enum


class BeamVerdict(Enum):
    AFFIRM = "affirm"
    DENY = "deny"
    SUSPEND = "suspend"
    ESCALATE = "escalate"


@dataclass
class BeamOutput:
    beam_name: str
    verdict: BeamVerdict
    confidence: float
    reasoning: str
    affected_atom_ids: List[str]
    produced_at_cycle: int


class PhilosophicalBeam(ABC):
    def __init__(self, name: str):
        self.name = name
        self.recent_outputs: List[BeamOutput] = []
        self.circularity_guard: Set[str] = set()

    @abstractmethod
    def reason(self, atoms, context: dict) -> BeamOutput:
        pass

    def can_reason_over(self, atom) -> bool:
        return atom.atom_id not in self.circularity_guard

    def register_produced_atoms(self, atom_ids: List[str]):
        self.circularity_guard.update(atom_ids)

    def clear_validated_atoms(self, atom_ids: List[str]):
        for aid in atom_ids:
            self.circularity_guard.discard(aid)


class HumeBeam(PhilosophicalBeam):
    def __init__(self):
        super().__init__("Hume")

    def reason(self, atoms, context) -> BeamOutput:
        scores = []
        for atom in atoms:
            if not self.can_reason_over(atom):
                continue
            vec = atom.correspondence_vector
            score = (vec.reality * 0.5 + vec.representation * 0.3 +
                    vec.continuity * 0.2)
            scores.append((atom, score))

        if not scores:
            return BeamOutput(self.name, BeamVerdict.SUSPEND, 0.5,
                            "No atoms available for reasoning", [], context.get("cycle", 0))

        avg_score = sum(s[1] for s in scores) / len(scores)
        verdict = (BeamVerdict.AFFIRM if avg_score > 0.7 else
                   BeamVerdict.DENY if avg_score < 0.3 else
                   BeamVerdict.SUSPEND)

        return BeamOutput(
            self.name, verdict, avg_score,
            f"Empirical score: {avg_score:.3f}",
            [a.atom_id for a, _ in scores],
            context.get("cycle", 0)
        )


class KantBeam(PhilosophicalBeam):
    def __init__(self):
        super().__init__("Kant")

    def reason(self, atoms, context) -> BeamOutput:
        scores = []
        for atom in atoms:
            if not self.can_reason_over(atom):
                continue
            vec = atom.correspondence_vector
            score = (vec.representation * 0.3 + vec.purpose * 0.4 +
                    vec.personhood * 0.3)
            scores.append((atom, score))

        if not scores:
            return BeamOutput(self.name, BeamVerdict.SUSPEND, 0.5,
                            "No atoms available", [], context.get("cycle", 0))

        avg_score = sum(s[1] for s in scores) / len(scores)
        verdict = (BeamVerdict.AFFIRM if avg_score > 0.7 else
                   BeamVerdict.DENY if avg_score < 0.3 else
                   BeamVerdict.SUSPEND)

        return BeamOutput(
            self.name, verdict, avg_score,
            f"Categorical score: {avg_score:.3f}",
            [a.atom_id for a, _ in scores],
            context.get("cycle", 0)
        )


class LockeBeam(PhilosophicalBeam):
    def __init__(self):
        super().__init__("Locke")

    def reason(self, atoms, context) -> BeamOutput:
        scores = []
        for atom in atoms:
            if not self.can_reason_over(atom):
                continue
            vec = atom.correspondence_vector
            score = (vec.personhood * 0.4 + vec.continuity * 0.3 +
                    vec.reality * 0.3)
            scores.append((atom, score))

        if not scores:
            return BeamOutput(self.name, BeamVerdict.SUSPEND, 0.5,
                            "No atoms available", [], context.get("cycle", 0))

        avg_score = sum(s[1] for s in scores) / len(scores)
        verdict = (BeamVerdict.AFFIRM if avg_score > 0.7 else
                   BeamVerdict.DENY if avg_score < 0.3 else
                   BeamVerdict.SUSPEND)

        return BeamOutput(
            self.name, verdict, avg_score,
            f"Natural law score: {avg_score:.3f}",
            [a.atom_id for a, _ in scores],
            context.get("cycle", 0)
        )


class SpinozaBeam(PhilosophicalBeam):
    def __init__(self):
        super().__init__("Spinoza")

    def reason(self, atoms, context) -> BeamOutput:
        scores = []
        for atom in atoms:
            if not self.can_reason_over(atom):
                continue
            vec = atom.correspondence_vector
            score = (vec.continuity * 0.4 + vec.purpose * 0.3 +
                    vec.representation * 0.3)
            scores.append((atom, score))

        if not scores:
            return BeamOutput(self.name, BeamVerdict.SUSPEND, 0.5,
                            "No atoms available", [], context.get("cycle", 0))

        avg_score = sum(s[1] for s in scores) / len(scores)
        min_score = min(s[1] for s in scores) if scores else 0
        if min_score < 0.4:
            verdict = BeamVerdict.ESCALATE
            reason = f"Incoherence detected: min dimension score {min_score:.3f}"
        else:
            verdict = (BeamVerdict.AFFIRM if avg_score > 0.75 else
                       BeamVerdict.DENY if avg_score < 0.25 else
                       BeamVerdict.SUSPEND)
            reason = f"Necessity score: {avg_score:.3f}"

        return BeamOutput(
            self.name, verdict, avg_score, reason,
            [a.atom_id for a, _ in scores],
            context.get("cycle", 0)
        )
