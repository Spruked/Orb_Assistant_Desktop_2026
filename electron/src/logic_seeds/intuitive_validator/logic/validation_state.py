"""Unity validation observations."""

import json
import time
from pathlib import Path
from typing import Dict, List, Tuple
from dataclasses import dataclass, asdict
from collections import deque


@dataclass
class UnityValidation:
    validation_id: str
    timestamp: float
    field_density: int
    symmetry_score: float
    unity_claimed: bool
    unity_validated: bool
    vector_congruence: float
    notes: str


class IntuitiveValidationCognition:
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.vault_path.mkdir(parents=True, exist_ok=True)

        self.validations: deque = deque(maxlen=5000)
        self.unity_history: List[Dict] = []

        self._load()

    def _load(self):
        log_file = self.vault_path / "unity_validations.jsonl"
        if log_file.exists():
            with open(log_file, "r") as f:
                for line in list(f)[-5000:]:
                    try:
                        self.validations.append(UnityValidation(**json.loads(line)))
                    except:
                        continue

    def record_unity_check(self, verdict: Dict, calculated: Dict) -> str:
        """Document unity claim verification."""
        v_id = f"unity_{int(time.time()*1000)}"

        claimed = verdict.get("unity_claimed", False)
        calc_symmetry = calculated.get("symmetry", 0)
        threshold = calculated.get("threshold", 0.88)

        validated = claimed and (calc_symmetry >= threshold)

        # Vector congruence
        orig_vec = verdict.get("unity_vector", (0, 0))
        calc_vec = calculated.get("vector", (0, 0))

        if isinstance(orig_vec, (list, tuple)) and isinstance(calc_vec, (list, tuple)):
            if len(orig_vec) >= 2 and len(calc_vec) >= 2:
                # Simple distance
                congruence = 1.0 - min(
                    1.0, abs(orig_vec[0] - calc_vec[0]) + abs(orig_vec[1] - calc_vec[1])
                )
            else:
                congruence = 0.0
        else:
            congruence = 0.0

        val = UnityValidation(
            validation_id=v_id,
            timestamp=time.time(),
            field_density=calculated.get("density", 0),
            symmetry_score=calc_symmetry,
            unity_claimed=claimed,
            unity_validated=validated,
            vector_congruence=congruence,
            notes="Unity claim checked against field geometry",
        )

        self.validations.append(val)

        with open(self.vault_path / "unity_validations.jsonl", "a") as f:
            f.write(json.dumps(asdict(val)) + "\n")

        return v_id

    def get_stats(self):
        if not self.validations:
            return {}
        validated = sum(1 for v in self.validations if v.unity_validated)
        return {
            "total_checks": len(self.validations),
            "unity_validated_rate": validated / len(self.validations),
            "avg_congruence": sum(v.vector_congruence for v in self.validations)
            / len(self.validations),
        }
