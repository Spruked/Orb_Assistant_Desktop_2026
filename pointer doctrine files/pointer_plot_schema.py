"""
Pointer Plot Map — shared schema.

This is the ONE data contract shared between Package A (scan/crawl) and
Package B (runtime). Do not modify field names without updating both sides.

Drop this into wherever Orb Weaver's existing Pydantic models live
(e.g. alongside CanonicalCapability).
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


class TargetType(str, Enum):
    NAV = "nav"
    HEADING = "heading"
    SECTION = "section"
    PARAGRAPH = "paragraph"
    FORM_FIELD = "form_field"
    BUTTON = "button"
    FAQ_ANSWER = "faq_answer"
    PRICE_CARD = "price_card"
    POLICY_LINE = "policy_line"
    DOWNLOAD = "download"
    OTHER = "other"


class AllowedAction(str, Enum):
    POINT = "point"
    POINT_AND_NAVIGATE = "point_and_navigate"
    POINT_AND_CONFIRM_NAVIGATE = "point_and_confirm_navigate"


class PlotStatus(str, Enum):
    ACTIVE = "active"
    STALE = "stale"
    UNRESOLVED = "unresolved"
    NEEDS_REVIEW = "needs_review"


class PlotSource(str, Enum):
    SCAN = "scan"
    LIVE_RECOVERY_PROMOTED = "live_recovery_promoted"


class PlotRecord(BaseModel):
    """
    One pointable destination on the site, as produced by Package A's scan.

    `semantic_locator` and `content_fingerprint` are the two primary
    resolution strategies the runtime tries, in that order, before
    falling back to accessibility-role matching or visual verification.
    Neither should ever be a fixed pixel coordinate — layouts move.
    """

    target_id: str = Field(..., description="Stable ID, survives re-scans if target is unchanged")
    page_route: str = Field(..., description="URL/route the target lives on")
    target_type: TargetType
    meaning: str = Field(..., description="Short human-readable description of what this target IS")
    intent_aliases: list[str] = Field(
        default_factory=list,
        description="Example visitor phrasings/questions this target answers",
    )
    content_fingerprint: str = Field(..., description="Text/content signature for fallback matching")
    semantic_locator: str = Field(..., description="DOM/accessibility-role locator, not fixed coords")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Scan-time confidence score")
    allowed_actions: list[AllowedAction] = Field(default_factory=lambda: [AllowedAction.POINT])
    status: PlotStatus = PlotStatus.ACTIVE
    last_verified_at: datetime = Field(default_factory=datetime.utcnow)
    source: PlotSource = PlotSource.SCAN

    class Config:
        use_enum_values = True


class CandidateCorrection(BaseModel):
    """
    Written by Package B (runtime) when a live recovery finds a target
    at a location that doesn't match the authoritative map.

    NEVER applied directly to the authoritative PlotRecord. Package A's
    scan process is the only writer of PlotRecord.status changes — see
    the promotion rule in promotion.py.
    """

    target_id: str
    new_locator: str = Field(..., description="Proposed replacement locator/fingerprint")
    evidence: str = Field(..., description="Verification method used, session context")
    observed_count: int = Field(default=1, ge=1)
    first_observed_at: datetime = Field(default_factory=datetime.utcnow)
    last_observed_at: datetime = Field(default_factory=datetime.utcnow)
