"""Primitive response cache runtime (ORB Standard V).

Resolves known tiny social inputs deterministically — before any routing,
tool call, provider, SKG, governance, or LLM layer.

Load order:
    1. Normalize input (lowercase, strip, collapse whitespace)
    2. Try alias lookup → canonical entry id
    3. Return entry response if found, else None (caller routes normally)
"""

import json
import re
import os
from pathlib import Path
from typing import Optional, Dict

_HERE = Path(__file__).parent

def _resolve_standard_root() -> Path:
    """
    Prefer R:\orb_core_standard (the canonical source).
    Fall back to the local copy in electron/src/ for offline / portable installs.
    """
    env = os.getenv("ORB_CORE_STANDARD_ROOT")
    if env:
        p = Path(env)
        if p.exists():
            return p
    # Infer from ORB_SYSTEM_ROOT: go up to drive root, then orb_core_standard
    sys_root = os.getenv("ORB_SYSTEM_ROOT")
    if sys_root:
        candidate = Path(sys_root).parent.parent / "orb_core_standard"
        if candidate.exists():
            return candidate
    # Walk up from this file
    for parent in [_HERE.parent, _HERE.parent.parent, _HERE.parent.parent.parent]:
        candidate = parent.parent / "orb_core_standard"
        if candidate.exists():
            return candidate
    return _HERE  # fallback: same directory

_STANDARD_ROOT = _resolve_standard_root()
_CACHE_PATH = Path(os.getenv("ORB_PRIMITIVE_CACHE_PATH", str(_STANDARD_ROOT / "primitive_response_cache.json")))
_ALIAS_PATH = Path(os.getenv("ORB_PRIMITIVE_ALIAS_PATH", str(_STANDARD_ROOT / "primitive_normalization_aliases.json")))

_WS_RE = re.compile(r"\s+")


def _load_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        import sys
        print(f"⚠️ PrimitiveCache: could not load {path}: {exc}", file=sys.stderr)
        return {}


class PrimitiveCache:
    """
    Thread-safe, reload-free primitive response resolver.
    Instantiate once and share across the orb lifetime.
    """

    def __init__(self):
        raw = _load_json(_CACHE_PATH)
        alias_raw = _load_json(_ALIAS_PATH)

        self._entries: Dict[str, Dict] = {
            entry["id"]: entry for entry in raw.get("entries", [])
        }
        self._aliases: Dict[str, str] = alias_raw.get("aliases", {})

    def resolve(self, raw_input: str) -> Optional[Dict]:
        """
        Try to resolve raw_input to a cached primitive response.

        Returns:
            {
                "response_text": str,
                "emotion": str,
                "route_class": "primitive",
                "entry_id": str,
            }
            or None if no primitive match.
        """
        normalized = self._normalize(raw_input)
        if not normalized:
            return None

        entry_id = self._aliases.get(normalized)
        if not entry_id:
            return None

        entry = self._entries.get(entry_id)
        if not entry:
            return None

        return {
            "response_text": entry["response"],
            "emotion": entry.get("emotion", "neutral"),
            "route_class": "primitive",
            "entry_id": entry_id,
        }

    @staticmethod
    def _normalize(text: str) -> str:
        """Lowercase, strip punctuation variants, collapse whitespace."""
        t = text.lower().strip()
        # Remove trailing punctuation repetition but keep ? and . for alias matching
        t = _WS_RE.sub(" ", t)
        return t
