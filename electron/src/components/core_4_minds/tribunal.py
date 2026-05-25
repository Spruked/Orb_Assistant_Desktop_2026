import json
import hashlib
from pathlib import Path
from typing import Dict, Any


class FourMindTribunal:
    """Loads four epistemic perspectives and produces deterministic shadow traces."""

    def __init__(self, skg_path: str = None):
        base = Path(skg_path) if skg_path else Path(__file__).resolve().parent
        self.minds = {
            "locke": self._load_mind(base / "hlocke" / "locke_empiricism_skg.json"),
            "hume": self._load_mind(base / "hhume" / "hume_skepticism_skg.json"),
            "kant": self._load_mind(base / "ikant" / "kant_critical_skg.json"),
            "spinoza": self._load_mind(base / "bspinoza" / "spinoza_monism_skg.json"),
        }

    def _load_mind(self, path: Path) -> Dict[str, Any]:
        if path.exists():
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"id": path.stem, "status": "missing"}

    def generate_epistemic_shadow(
        self, stimulus: Dict[str, Any]
    ) -> Dict[str, Dict[str, Any]]:
        """Return deterministic confidence traces for each mind."""
        canonical = json.dumps(stimulus, sort_keys=True)
        base_hash = int(hashlib.sha256(canonical.encode()).hexdigest(), 16)
        shadows = {}
        for idx, (mind, payload) in enumerate(self.minds.items()):
            confidence = ((base_hash >> (idx * 8)) & 0xFF) / 255
            shadows[mind] = {
                "confidence": round(0.5 + 0.5 * confidence, 3),
                "reference": payload.get("id", mind),
                "domain": payload.get("domain", "unknown"),
            }
        return shadows
