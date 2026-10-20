from __future__ import annotations

import json
import hashlib
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pointer_plot_schema import (
    AllowedAction,
    PlotRecord,
    PlotSource,
    PlotStatus,
    TargetType,
    normalize_pointer_plot,
)


def extract_pointer_plots(scan_payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_items = scan_payload.get("pointer_plots") or scan_payload.get("plots") or []
    if not isinstance(raw_items, list):
        raw_items = []
    return [asdict(normalize_pointer_plot(item)) for item in raw_items if isinstance(item, dict)]


def extract_scan_file(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return []
    return extract_pointer_plots(payload)


def _fingerprint(text: str) -> str:
    normalized = " ".join(text.strip().lower().split())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:16]


def _desktop_target_type(element: dict[str, Any]) -> TargetType:
    raw = str(element.get("type") or element.get("role") or element.get("kind") or "other").lower()
    mapping = {
        "navigation": TargetType.NAV,
        "nav": TargetType.NAV,
        "heading": TargetType.HEADING,
        "section": TargetType.SECTION,
        "text": TargetType.PARAGRAPH,
        "paragraph": TargetType.PARAGRAPH,
        "edit": TargetType.FORM_FIELD,
        "textbox": TargetType.FORM_FIELD,
        "form_field": TargetType.FORM_FIELD,
        "button": TargetType.BUTTON,
        "link": TargetType.BUTTON,
        "download": TargetType.DOWNLOAD,
    }
    return mapping.get(raw, TargetType.OTHER)


def extract_plot_records_from_desktop_scene(
    surface_route: str,
    scene_elements: list[dict[str, Any]],
) -> list[PlotRecord]:
    records: list[PlotRecord] = []
    for element in scene_elements:
        text = str(element.get("text") or element.get("name") or element.get("label") or "").strip()
        if not text:
            continue
        locator = str(
            element.get("semantic_locator")
            or element.get("automation_id")
            or element.get("selector")
            or ""
        ).strip()
        if not locator:
            continue
        target_type = _desktop_target_type(element)
        actions = [AllowedAction.POINT]
        if target_type in {TargetType.NAV, TargetType.BUTTON}:
            actions.append(AllowedAction.POINT_AND_CONFIRM_NAVIGATE)
        fingerprint = _fingerprint(text)
        aliases = element.get("intent_hints") if isinstance(element.get("intent_hints"), list) else []
        records.append(
            PlotRecord(
                target_id=f"{surface_route}::{fingerprint[:12]}",
                page_route=surface_route,
                target_type=target_type,
                meaning=text if len(text) <= 120 else text[:117] + "...",
                intent_aliases=[str(alias) for alias in aliases],
                content_fingerprint=fingerprint,
                semantic_locator=locator,
                confidence=max(0.0, min(1.0, float(element.get("confidence", 0.75)))),
                allowed_actions=actions,
                status=PlotStatus.ACTIVE,
                last_verified_at=datetime.now(timezone.utc),
                source=PlotSource.SCAN,
            )
        )
    return records


if __name__ == "__main__":
    import sys

    if len(sys.argv) != 2:
        raise SystemExit("usage: scan_extraction.py <scan.json>")
    print(json.dumps(extract_scan_file(sys.argv[1]), indent=2))
