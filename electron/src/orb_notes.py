#!/usr/bin/env python3
"""CaliNotes — persistent note-taking and session management for the Orb."""

import json
import re
from datetime import datetime
from pathlib import Path


class CaliNotes:
    def __init__(self, base_path):
        self.base_path = Path(base_path).expanduser().resolve()
        self.base_path.mkdir(parents=True, exist_ok=True)

    def normalize_topic(self, topic: str) -> str:
        folder = str(topic or "general_notes").lower().replace(" ", "_").strip()
        folder = re.sub(r"[^a-z0-9_\-]+", "_", folder)
        folder = re.sub(r"_+", "_", folder).strip("_")
        return folder or "general_notes"

    def _existing_subject_folder(self, normalized_topic: str):
        exact = self.base_path / normalized_topic
        if exact.exists():
            return exact

        tokens = {token for token in normalized_topic.split("_") if len(token) > 2}
        if not tokens:
            return None

        best_path = None
        best_score = 0.0
        for path in self.base_path.iterdir():
            if not path.is_dir():
                continue
            existing_tokens = {token for token in path.name.split("_") if len(token) > 2}
            if not existing_tokens:
                continue
            overlap = len(tokens & existing_tokens)
            score = overlap / max(len(tokens), len(existing_tokens))
            if score > best_score:
                best_score = score
                best_path = path

        return best_path if best_score >= 0.67 else None

    def get_subject_path(self, topic):
        normalized = self.normalize_topic(topic)
        path = self._existing_subject_folder(normalized) or self.base_path / normalized
        path.mkdir(parents=True, exist_ok=True)
        return path

    def create_session(self, topic):
        subject_path = self.get_subject_path(topic)
        filename = f"session_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.txt"
        full_path = subject_path / filename

        with full_path.open("w", encoding="utf-8") as handle:
            handle.write(f"# Session: {topic}\n\n")

        return full_path

    def append(self, session_path, text):
        path = Path(session_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(str(text).rstrip() + "\n")
        return path

    def append_source(self, topic, source):
        subject_path = self.get_subject_path(topic)
        sources_path = subject_path / "sources.json"
        sources = self._read_json_list(sources_path)
        if not isinstance(sources, list):
            sources = []

        normalized = {
            "url": source.get("url") or source.get("source"),
            "title": source.get("title"),
            "timestamp": datetime.now().isoformat(),
            "confidence": source.get("confidence"),
            "domain": source.get("domain"),
            "query": source.get("query"),
        }
        if not normalized["url"] and not normalized["title"]:
            return sources_path

        key = (normalized.get("url") or normalized.get("title") or "").strip().lower()
        existing_keys = {
            (item.get("url") or item.get("title") or "").strip().lower()
            for item in sources
            if isinstance(item, dict)
        }
        if key not in existing_keys:
            sources.append(normalized)

        sources_path.write_text(json.dumps(sources, indent=2, ensure_ascii=False), encoding="utf-8")
        return sources_path

    def _read_json_list(self, path):
        if not path.exists():
            return []
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            return []
        return payload if isinstance(payload, list) else []

    def store_lightweight_summary(self, topic, query, key_points, sources=None):
        subject_path = self.get_subject_path(topic)
        highlights_path = subject_path / "passive_highlights.json"
        highlights = self._read_json_list(highlights_path)
        normalized_points = [
            " ".join(str(point or "").split())
            for point in (key_points or [])
            if str(point or "").strip()
        ][:8]
        if not normalized_points:
            return highlights_path

        record = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "key_points": normalized_points,
            "sources": [
                {
                    "url": source.get("url") or source.get("source"),
                    "title": source.get("title"),
                    "confidence": source.get("confidence"),
                    "domain": source.get("domain"),
                }
                for source in (sources or [])
                if isinstance(source, dict)
            ][:8],
        }
        signature = json.dumps(
            {"query": record["query"], "key_points": record["key_points"]},
            sort_keys=True,
            ensure_ascii=False,
        )
        existing = {
            json.dumps(
                {"query": item.get("query"), "key_points": item.get("key_points")},
                sort_keys=True,
                ensure_ascii=False,
            )
            for item in highlights
            if isinstance(item, dict)
        }
        if signature not in existing:
            highlights.append(record)
        highlights = highlights[-50:]
        highlights_path.write_text(json.dumps(highlights, indent=2, ensure_ascii=False), encoding="utf-8")
        return highlights_path

    def promote_passive_highlights(self, topic, session_path, limit=10):
        subject_path = self.get_subject_path(topic)
        highlights = self._read_json_list(subject_path / "passive_highlights.json")
        points = []
        seen = set()
        for record in reversed(highlights):
            for point in record.get("key_points", []) if isinstance(record, dict) else []:
                key = str(point).strip().lower()
                if key and key not in seen:
                    seen.add(key)
                    points.append(str(point).strip())
                if len(points) >= limit:
                    break
            if len(points) >= limit:
                break
        if not points:
            return []
        self.append(session_path, "\nSaved highlights:")
        for point in points:
            self.append(session_path, f"- {point}")
        return points

    def write_summary(self, topic, summary, key_points=None, sources=None):
        subject_path = self.get_subject_path(topic)
        summary_path = subject_path / "summary.txt"
        clean_summary = " ".join(str(summary or "").split())
        clean_points = [
            " ".join(str(point or "").split())
            for point in (key_points or [])
            if str(point or "").strip()
        ][:10]
        source_count = len(sources or [])
        lines = [
            f"# Summary: {topic}",
            "",
            f"Updated: {datetime.now().isoformat()}",
            f"Source count: {source_count}",
            "",
            "## Distilled Summary",
            clean_summary or "No confirmed summary recorded yet.",
        ]
        if clean_points:
            lines.extend(["", "## Key Points"])
            lines.extend(f"- {point}" for point in clean_points)
        summary_path.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8")
        return summary_path

    def read_summary(self, topic):
        summary_path = self.get_subject_path(topic) / "summary.txt"
        if not summary_path.exists():
            return ""
        return summary_path.read_text(encoding="utf-8", errors="replace").strip()
