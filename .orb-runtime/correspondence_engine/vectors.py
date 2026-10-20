"""
CorrespondenceVector — MANDATORY / FROZEN.

Replaces the bare `dict` originally proposed for correspondence
vectors. A bare dict allowed silent misspellings, missing dimensions,
and out-of-range values to pass through undetected — the same
failure class that broke the v0.2 scoring engine. This class makes
that class of error impossible to construct.

NOTE: nothing in this file computes a CorrespondenceVector from a
claim or from evidence. See gaps.py: GAP_A — no module currently
owns that computation. This file only defines the validated shape
once a vector exists.
"""

from dataclasses import dataclass, fields


@dataclass(frozen=True)
class CorrespondenceVector:
    reality: float
    representation: float
    purpose: float
    personhood: float
    continuity: float

    def __post_init__(self):
        for f in fields(self):
            v = getattr(self, f.name)
            if not (0.0 <= v <= 1.0):
                raise ValueError(f"{f.name} must be in [0,1], got {v}")

    def as_tuple(self):
        return (
            self.reality,
            self.representation,
            self.purpose,
            self.personhood,
            self.continuity,
        )

    @staticmethod
    def dimension_names():
        return ("reality", "representation", "purpose", "personhood", "continuity")
