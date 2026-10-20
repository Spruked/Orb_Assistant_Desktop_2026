from __future__ import annotations

import csv
import io
import os
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pointer_plot_schema import PlotRecord


@dataclass(frozen=True)
class OCRVisualMatch:
    text: str
    confidence: float
    x: int
    y: int
    width: int
    height: int
    locator: str


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", value.lower()) if len(token) > 1}


def parse_tesseract_tsv(tsv: str) -> list[OCRVisualMatch]:
    matches: list[OCRVisualMatch] = []
    for row in csv.DictReader(io.StringIO(tsv), delimiter="\t"):
        text = str(row.get("text") or "").strip()
        if not text:
            continue
        try:
            confidence = max(0.0, min(1.0, float(row.get("conf", "-1")) / 100.0))
            x = int(row.get("left", "0"))
            y = int(row.get("top", "0"))
            width = int(row.get("width", "0"))
            height = int(row.get("height", "0"))
        except (TypeError, ValueError):
            continue
        if confidence <= 0.0:
            continue
        matches.append(
            OCRVisualMatch(
                text=text,
                confidence=confidence,
                x=x,
                y=y,
                width=width,
                height=height,
                locator=f"ocr:{x},{y},{width},{height}:{text}",
            )
        )
    return matches


def match_record_to_ocr(record: PlotRecord, regions: list[OCRVisualMatch]) -> OCRVisualMatch | None:
    expected = _tokens(" ".join([record.meaning, *record.intent_aliases]))
    if not expected:
        return None
    ranked: list[tuple[float, OCRVisualMatch]] = []
    for region in regions:
        observed = _tokens(region.text)
        overlap = len(expected & observed) / max(1, len(expected))
        score = overlap * 0.75 + region.confidence * 0.25
        if overlap > 0:
            ranked.append((score, region))
    if not ranked:
        return None
    score, match = max(ranked, key=lambda item: item[0])
    return match if score >= 0.45 else None


def run_tesseract_visual_verification(
    image_path: str | Path,
    record: PlotRecord,
    lang: str = "eng",
    psm: int = 11,
) -> OCRVisualMatch | None:
    executable = Path(os.getenv("ORB_TESSERACT_BIN", r"C:\Program Files\Tesseract-OCR\tesseract.exe"))
    if not executable.is_file():
        return None
    env = os.environ.copy()
    env.setdefault("TESSDATA_PREFIX", str(executable.parent / "tessdata"))
    result = subprocess.run(
        [str(executable), str(Path(image_path)), "stdout", "-l", lang, "--psm", str(psm), "tsv"],
        capture_output=True,
        text=True,
        timeout=45,
        env=env,
    )
    if result.returncode != 0:
        return None
    return match_record_to_ocr(record, parse_tesseract_tsv(result.stdout))
