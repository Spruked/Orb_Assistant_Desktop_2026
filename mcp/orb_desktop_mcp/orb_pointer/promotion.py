from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from pointer_plot_schema import CandidateCorrection, PlotRecord, PlotSource, PlotStatus


PROMOTION_THRESHOLD_SESSIONS = 3
STALE_HIT_WINDOW = timedelta(hours=24)
STALE_HIT_THRESHOLD = 3


def group_corrections_by_target(
    corrections: list[CandidateCorrection],
) -> dict[str, list[CandidateCorrection]]:
    grouped: dict[str, list[CandidateCorrection]] = defaultdict(list)
    for correction in corrections:
        grouped[correction.target_id].append(correction)
    return grouped


def should_promote(
    target_id: str,
    corrections: list[CandidateCorrection],
    threshold: int = PROMOTION_THRESHOLD_SESSIONS,
) -> tuple[bool, str | None]:
    by_locator: dict[str, int] = defaultdict(int)
    for correction in corrections:
        if correction.target_id == target_id:
            by_locator[correction.new_locator] += correction.observed_count
    for locator, count in by_locator.items():
        if count >= threshold:
            return True, locator
    return False, None


def apply_promotion(record: PlotRecord, new_locator: str) -> PlotRecord:
    return replace(
        record,
        semantic_locator=new_locator,
        status=PlotStatus.ACTIVE,
        source=PlotSource.LIVE_RECOVERY_PROMOTED,
        last_verified_at=datetime.now(timezone.utc),
    )


def evaluate_stale_hits(
    target_id: str,
    stale_hit_timestamps: list[datetime],
    window: timedelta = STALE_HIT_WINDOW,
    threshold: int = STALE_HIT_THRESHOLD,
) -> bool:
    del target_id
    cutoff = datetime.now(timezone.utc) - window
    normalized = [timestamp if timestamp.tzinfo else timestamp.replace(tzinfo=timezone.utc) for timestamp in stale_hit_timestamps]
    return len([timestamp for timestamp in normalized if timestamp >= cutoff]) >= threshold


def mark_needs_review(record: PlotRecord) -> PlotRecord:
    return replace(record, status=PlotStatus.NEEDS_REVIEW)
