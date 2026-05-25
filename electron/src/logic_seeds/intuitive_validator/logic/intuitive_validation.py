"""Unity verification - geometric witness.

FROZEN INTERFACE v1.0.0-final
============================
This validation layer is OBSERVATIONAL ONLY.

Core logic MUST NOT import from this module.
Core logic MUST ONLY emit verdicts TO this layer for witnessing.

Any changes to this interface require full system validation.
"""

from pathlib import Path
from typing import Dict
from .validation_state import IntuitiveValidationCognition


class IntuitiveValidator:
    def __init__(self, worker_root: Path):
        self.root = worker_root
        self.vault_path = worker_root / "vault"
        self.cognition = IntuitiveValidationCognition(self.vault_path)

        self.symmetry_threshold = 0.88

    def validate_verdict(self, verdict_package: Dict) -> Dict:
        """Witness unity claims against actual field geometry."""
        original = verdict_package.get("verdict", {})
        hlsf_data = verdict_package.get("hlsf_context", {})

        # Parallel geometric check
        geo_check = self._check_field_geometry(hlsf_data, original)

        val_id = self.cognition.record_unity_check(original, geo_check)

        return {
            "original_verdict": original,
            "validation_layer": {
                "validator": "intuitive",
                "validation_id": val_id,
                "field_density_check": geo_check["density"],
                "symmetry_calculated": geo_check["symmetry"],
                "unity_threshold": self.symmetry_threshold,
                "vector_congruence": geo_check.get("congruence", 0),
                "geometry_validated": geo_check["symmetry"] >= self.symmetry_threshold,
            },
            "delivery_status": "witnessed",
        }

    def _check_field_geometry(self, hlsf_data: Dict, verdict: Dict) -> Dict:
        """Re-calculate field geometry independently."""
        field_map = hlsf_data.get("field_map", {})

        if not field_map:
            return {"density": 0, "symmetry": 0, "vector": (0, 0)}

        density = len(field_map)

        # Simple symmetry calc
        coords = []
        for node in field_map.values():
            c = (
                node.get("coordinates", [0, 0])
                if isinstance(node, dict)
                else getattr(node, "coordinates", [0, 0])
            )
            if c and len(c) >= 2:
                coords.append((float(c[0]), float(c[1])))

        if len(coords) < 2:
            symmetry = 0.0
        else:
            mirrors = 0
            for i, c1 in enumerate(coords):
                for c2 in coords[i + 1 :]:
                    if abs(c1[0] + c2[0]) < 0.3 and abs(c1[1] - c2[1]) < 0.3:
                        mirrors += 1
            total = len(coords) * (len(coords) - 1) / 2
            symmetry = mirrors / total if total > 0 else 0.0

        # Centroid vector
        if coords:
            cx = sum(c[0] for c in coords) / len(coords)
            cy = sum(c[1] for c in coords) / len(coords)
            vector = (cx, cy)
        else:
            vector = (0, 0)

        return {
            "density": density,
            "symmetry": symmetry,
            "vector": vector,
            "threshold": self.symmetry_threshold,
        }

    def get_status(self):
        return {"role": "geometric_witness", "stats": self.cognition.get_stats()}
