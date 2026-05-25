#!/usr/bin/env python3
"""Ingest a local orb skin into the sovereign skin vault."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

try:
    from PIL import Image
except ImportError:  # pragma: no cover - optional runtime dependency
    Image = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True, help="Path to the source image")
    parser.add_argument("--skins-dir", required=True, help="Destination skins directory")
    return parser.parse_args()


def average_rgb(image_path: Path) -> list[int]:
    if Image is None:
        return [128, 128, 128]

    with Image.open(image_path) as img:
        img = img.convert("RGB")
        img.thumbnail((64, 64))
        pixels = list(img.getdata())
        count = max(1, len(pixels))
        r = sum(pixel[0] for pixel in pixels) // count
        g = sum(pixel[1] for pixel in pixels) // count
        b = sum(pixel[2] for pixel in pixels) // count
        return [int(r), int(g), int(b)]


def main() -> None:
    args = parse_args()
    source = Path(args.source).expanduser().resolve()
    skins_dir = Path(args.skins_dir).expanduser().resolve()
    metadata_dir = skins_dir / "metadata"

    if not source.exists() or not source.is_file():
        raise SystemExit(f"Source file not found: {source}")

    skins_dir.mkdir(parents=True, exist_ok=True)
    metadata_dir.mkdir(parents=True, exist_ok=True)

    digest = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    extension = source.suffix.lower() or ".png"
    filename = f"{source.stem}_{digest}{extension}"
    destination = skins_dir / filename

    shutil.copy2(source, destination)

    avg_rgb = average_rgb(destination)
    metadata = {
        "filename": filename,
        "source_path": str(source),
        "stored_path": str(destination),
        "imported_at": datetime.now(timezone.utc).isoformat(),
        "average_rgb": avg_rgb,
        "logic_tint": {
            "deductive": {"hue_rotate_deg": 0, "brightness": 1.0},
            "inductive": {"hue_rotate_deg": 48, "brightness": 1.04},
            "intuitive": {"hue_rotate_deg": -26, "brightness": 1.08},
        },
    }

    metadata_path = metadata_dir / f"{destination.stem}.json"
    metadata_path.write_text(json.dumps(metadata, indent=2), encoding="utf-8")

    print(
        json.dumps(
            {
                "filename": filename,
                "metadata_path": str(metadata_path),
                "average_rgb": avg_rgb,
            }
        )
    )


if __name__ == "__main__":
    main()
