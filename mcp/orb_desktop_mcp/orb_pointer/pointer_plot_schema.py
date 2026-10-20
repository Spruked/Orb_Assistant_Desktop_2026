from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


POINTER_SOURCES = {"cursor", "scan", "voice", "system", "tamp", "orbweaver"}
POINTER_INTENTS = {
    "observe",
    "hover_context",
    "point_at",
    "explain",
    "select",
    "open",
    "dismiss",
    "operator_override",
}
POINTER_FRAME_TYPES = {"virtual_desktop", "monitor", "window", "capture"}
POINTER_TARGET_KINDS = {
    "visible_text",
    "ui_element",
    "window",
    "icon",
    "region",
    "cursor_relative",
    "unknown",
}


@dataclass(frozen=True)
class PointerTarget:
    kind: str = "unknown"
    label: str | None = None
    description: str | None = None
    selector: str | None = None


@dataclass(frozen=True)
class PointerFrame:
    type: str = "virtual_desktop"
    monitor_id: str | None = None
    capture_id: str | None = None
    window_id: str | None = None


@dataclass(frozen=True)
class PointerPoint:
    x: float
    y: float
    monitor_id: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


@dataclass(frozen=True)
class PointerBoundingBox:
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class PointerPlot:
    id: str
    source: str
    intent: str
    point: PointerPoint
    confidence: float
    target: PointerTarget | None = None
    frame: PointerFrame = field(default_factory=PointerFrame)
    bbox: PointerBoundingBox | None = None
    label: str | None = None
    evidence: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def _number(value: Any, fallback: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return fallback


def _normalize_target(value: Any) -> PointerTarget | None:
    if not isinstance(value, dict):
        return None
    kind = str(value.get("kind") or "unknown")
    return PointerTarget(
        kind=kind if kind in POINTER_TARGET_KINDS else "unknown",
        label=value.get("label"),
        description=value.get("description"),
        selector=value.get("selector"),
    )


def _normalize_frame(value: Any) -> PointerFrame:
    frame = value if isinstance(value, dict) else {}
    frame_type = str(frame.get("type") or "virtual_desktop")
    return PointerFrame(
        type=frame_type if frame_type in POINTER_FRAME_TYPES else "virtual_desktop",
        monitor_id=frame.get("monitorId") or frame.get("monitor_id"),
        capture_id=frame.get("captureId") or frame.get("capture_id"),
        window_id=frame.get("windowId") or frame.get("window_id"),
    )


def _normalize_bbox(value: Any) -> PointerBoundingBox | None:
    if not isinstance(value, dict):
        return None
    return PointerBoundingBox(
        x=_number(value.get("x")),
        y=_number(value.get("y")),
        width=max(0.0, _number(value.get("width"))),
        height=max(0.0, _number(value.get("height"))),
    )


def normalize_pointer_plot(payload: dict[str, Any]) -> PointerPlot:
    point = payload.get("point") if isinstance(payload.get("point"), dict) else {}
    source = str(payload.get("source") or "system")
    intent = str(payload.get("intent") or "observe")
    confidence = max(0.0, min(1.0, _number(payload.get("confidence"), 0.0)))
    evidence = payload.get("evidence") if isinstance(payload.get("evidence"), list) else []

    return PointerPlot(
        id=str(payload.get("id") or f"pointer-{int(datetime.now().timestamp() * 1000)}"),
        source=source if source in POINTER_SOURCES else "system",
        intent=intent if intent in POINTER_INTENTS else "observe",
        point=PointerPoint(
            x=_number(point.get("x")),
            y=_number(point.get("y")),
            monitor_id=point.get("monitorId") or point.get("monitor_id"),
            timestamp=str(point.get("timestamp") or datetime.now(timezone.utc).isoformat()),
        ),
        confidence=confidence,
        target=_normalize_target(payload.get("target")),
        frame=_normalize_frame(payload.get("frame")),
        bbox=_normalize_bbox(payload.get("bbox")),
        label=payload.get("label"),
        evidence=[str(item) for item in evidence],
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {},
    )


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


@dataclass(frozen=True)
class PlotRecord:
    target_id: str
    page_route: str
    target_type: TargetType
    meaning: str
    intent_aliases: list[str]
    content_fingerprint: str
    semantic_locator: str
    confidence: float
    allowed_actions: list[AllowedAction]
    status: PlotStatus
    last_verified_at: datetime
    source: PlotSource


@dataclass(frozen=True)
class CandidateCorrection:
    target_id: str
    new_locator: str
    evidence: str
    observed_count: int
    first_observed_at: datetime
    last_observed_at: datetime


def normalize_plot_record(payload: dict[str, Any]) -> PlotRecord:
    verified = payload.get("last_verified_at")
    if isinstance(verified, str):
        verified = datetime.fromisoformat(verified.replace("Z", "+00:00"))
    if not isinstance(verified, datetime):
        verified = datetime.now(timezone.utc)
    actions = payload.get("allowed_actions") if isinstance(payload.get("allowed_actions"), list) else []
    return PlotRecord(
        target_id=str(payload.get("target_id") or ""),
        page_route=str(payload.get("page_route") or "desktop://unknown"),
        target_type=TargetType(str(payload.get("target_type") or TargetType.OTHER.value)),
        meaning=str(payload.get("meaning") or ""),
        intent_aliases=[str(item) for item in payload.get("intent_aliases", [])],
        content_fingerprint=str(payload.get("content_fingerprint") or ""),
        semantic_locator=str(payload.get("semantic_locator") or ""),
        confidence=max(0.0, min(1.0, _number(payload.get("confidence"), 0.0))),
        allowed_actions=[AllowedAction(str(item)) for item in actions],
        status=PlotStatus(str(payload.get("status") or PlotStatus.ACTIVE.value)),
        last_verified_at=verified,
        source=PlotSource(str(payload.get("source") or PlotSource.SCAN.value)),
    )
