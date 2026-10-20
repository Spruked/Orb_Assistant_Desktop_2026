"""
Package A — Pointer Plot Map extraction.

This runs as a step inside Orb Weaver's EXISTING crawl. It does not
replace or duplicate the existing content classifier — it consumes
whatever the existing crawler already produces per page and reshapes
qualifying elements into PlotRecords.

TODO(integration): replace `extract_candidates_from_page` internals
with calls into Orb Weaver's actual page-parsing/classification
output. The function signature and return contract below are what
matter — the body is a placeholder showing the shape of the logic.
"""

from __future__ import annotations

import hashlib
from datetime import datetime

from pointer_plot_schema import AllowedAction, PlotRecord, PlotSource, PlotStatus, TargetType


def _fingerprint(text: str) -> str:
    """Stable content fingerprint for fallback matching."""
    normalized = " ".join(text.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def extract_candidates_from_page(
    page_route: str,
    # TODO(integration): this should be whatever structured object
    # Orb Weaver's existing crawler already produces per page —
    # e.g. parsed DOM tree, existing content-classification output,
    # accessibility tree, etc. Replace `page_elements` with the real type.
    page_elements: list[dict],
) -> list[PlotRecord]:
    """
    Turns one page's classified elements into PlotRecords.

    Expected shape of each item in `page_elements` (adjust to match
    what the existing crawler actually emits):
        {
            "type": "heading" | "paragraph" | "button" | "form_field" | ...,
            "text": str,
            "semantic_locator": str,   # e.g. accessibility role path, stable selector
            "intent_hints": list[str], # phrases the existing classifier
                                        # already associates with this element, if any
            "confidence": float,       # existing classifier's confidence, if available
        }
    """
    records: list[PlotRecord] = []

    for element in page_elements:
        target_type = _map_element_type(element.get("type", "other"))
        if target_type is None:
            continue  # not a pointable target — skip

        text = element.get("text", "").strip()
        if not text:
            continue

        target_id = f"{page_route}::{_fingerprint(text)[:12]}"

        records.append(
            PlotRecord(
                target_id=target_id,
                page_route=page_route,
                target_type=target_type,
                meaning=_summarize_meaning(text, target_type),
                intent_aliases=element.get("intent_hints", []),
                content_fingerprint=_fingerprint(text),
                semantic_locator=element["semantic_locator"],
                confidence=element.get("confidence", 0.75),
                allowed_actions=_default_actions(target_type),
                status=PlotStatus.ACTIVE,
                last_verified_at=datetime.utcnow(),
                source=PlotSource.SCAN,
            )
        )

    return records


def _map_element_type(raw_type: str) -> TargetType | None:
    mapping = {
        "nav": TargetType.NAV,
        "heading": TargetType.HEADING,
        "section": TargetType.SECTION,
        "paragraph": TargetType.PARAGRAPH,
        "form_field": TargetType.FORM_FIELD,
        "button": TargetType.BUTTON,
        "faq_answer": TargetType.FAQ_ANSWER,
        "price_card": TargetType.PRICE_CARD,
        "policy_line": TargetType.POLICY_LINE,
        "download": TargetType.DOWNLOAD,
    }
    return mapping.get(raw_type, TargetType.OTHER if raw_type else None)


def _summarize_meaning(text: str, target_type: TargetType) -> str:
    # TODO(integration): consider calling the LLM articulation layer
    # here for a genuinely short summary, per the "LLM as optional
    # articulation layer only" doctrine. Placeholder: naive truncation.
    snippet = text if len(text) <= 80 else text[:77] + "..."
    return f"[{target_type.value}] {snippet}"


def _default_actions(target_type: TargetType) -> list[AllowedAction]:
    # Nav items and buttons are the only types allowed to imply
    # navigation by default; everything else is point-only until
    # explicitly configured otherwise (owner-level setting, not scan-time guess).
    if target_type in (TargetType.NAV, TargetType.BUTTON):
        return [AllowedAction.POINT, AllowedAction.POINT_AND_CONFIRM_NAVIGATE]
    return [AllowedAction.POINT]
