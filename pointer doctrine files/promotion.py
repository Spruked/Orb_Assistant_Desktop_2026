"""
Promotion rule — the guardrail that prevents one weird page state
(A/B test, cookie banner, logged-in variant, responsive layout) from
corrupting the authoritative map from a single visitor session.

This module is called ONLY by Package A's scan process. Package B
(runtime) never imports this — it only writes CandidateCorrection
records and never touches PlotRecord.status.

TODO(integration): wire `load_candidate_corrections` and
`save_plot_record` to your actual ORB context store (wherever Orb
Weaver already persists scan output). Stubbed here with an in-memory
interface so the promotion LOGIC is complete and testable independent
of storage.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta

from pointer_plot_schema import CandidateCorrection, PlotRecord, PlotSource, PlotStatus

# Conservative default — flagged as an open decision in the doctrine doc.
# Raise or lower based on real traffic once this is live.
PROMOTION_THRESHOLD_SESSIONS = 3

# Repeated-failure escalation window: if the same target keeps failing
# live recovery within this window, stop attempting live recovery for
# it and flag needs_review instead of making every visitor wait.
STALE_HIT_WINDOW = timedelta(hours=24)
STALE_HIT_THRESHOLD = 3


def group_corrections_by_target(
    corrections: list[CandidateCorrection],
) -> dict[str, list[CandidateCorrection]]:
    grouped: dict[str, list[CandidateCorrection]] = defaultdict(list)
    for c in corrections:
        grouped[c.target_id].append(c)
    return grouped


def should_promote(
    target_id: str,
    corrections: list[CandidateCorrection],
    threshold: int = PROMOTION_THRESHOLD_SESSIONS,
) -> tuple[bool, str | None]:
    """
    Returns (should_promote, winning_locator).

    Promotion happens only when the SAME correction (same new_locator)
    has been independently observed across `threshold` or more sessions.
    Corrections proposing different locators for the same target do
    NOT combine their counts — that would let two conflicting fixes
    average into a false promotion.
    """
    by_locator: dict[str, int] = defaultdict(int)
    for c in corrections:
        if c.target_id != target_id:
            continue
        by_locator[c.new_locator] += c.observed_count

    for locator, count in by_locator.items():
        if count >= threshold:
            return True, locator

    return False, None


def apply_promotion(record: PlotRecord, new_locator: str) -> PlotRecord:
    """
    Produces the updated PlotRecord after promotion criteria are met.
    Called only from within Package A's scan/rescan job — never from
    the live runtime path.
    """
    return record.copy(
        update={
            "semantic_locator": new_locator,
            "status": PlotStatus.ACTIVE,
            "source": PlotSource.LIVE_RECOVERY_PROMOTED,
            "last_verified_at": datetime.utcnow(),
        }
    )


def evaluate_stale_hits(
    target_id: str,
    stale_hit_timestamps: list[datetime],
    window: timedelta = STALE_HIT_WINDOW,
    threshold: int = STALE_HIT_THRESHOLD,
) -> bool:
    """
    Returns True if this target has failed live recovery often enough,
    recently enough, that Package B should stop attempting live
    recovery for it and fall straight to voice-only + needs_review.

    TODO(integration): stale_hit_timestamps should come from wherever
    Package B logs failed-recovery events for a target_id. This
    function is pure logic — wire the actual event log separately.
    """
    cutoff = datetime.utcnow() - window
    recent_hits = [ts for ts in stale_hit_timestamps if ts >= cutoff]
    return len(recent_hits) >= threshold


def mark_needs_review(record: PlotRecord) -> PlotRecord:
    return record.copy(update={"status": PlotStatus.NEEDS_REVIEW})
