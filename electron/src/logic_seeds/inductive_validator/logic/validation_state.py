"""Pattern validation observation records."""

import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List
from dataclasses import dataclass, asdict
from collections import deque


@dataclass
class PatternValidation:
    validation_id: str
    timestamp: float
    verdict_pattern: str
    predicted_continuation: str
    historical_support: float
    alignment: str  # "supported", "contradicted", "novel"
    observation_count: int
    notes: List[str]


class InductiveValidationCognition:
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.vault_path.mkdir(parents=True, exist_ok=True)

        self.validations: deque = deque(maxlen=5000)
        self.pattern_support: Dict[str, Dict] = {}

        self._load()

    def _load(self):
        log_file = self.vault_path / "pattern_validations.jsonl"
        if log_file.exists():
            with open(log_file, "r") as f:
                for line in list(f)[-5000:]:
                    try:
                        self.validations.append(PatternValidation(**json.loads(line)))
                    except:
                        continue

        # Load historical pattern support data
        support_file = self.vault_path / "pattern_support.json"
        if support_file.exists():
            with open(support_file, "r") as f:
                self.pattern_support = json.load(f)

    def record_validation(self, verdict: Dict, historical_check: Dict) -> str:
        """Document pattern validation."""
        v_id = f"val_{int(time.time()*1000)}"

        pattern = verdict.get("pattern", "unknown")
        prediction = verdict.get("predicted_next", "unknown")

        support = historical_check.get("frequency", 0)

        if support > 0.7:
            align = "supported"
        elif support > 0.3:
            align = "partial_support"
        else:
            align = "novel_pattern"

        val = PatternValidation(
            validation_id=v_id,
            timestamp=time.time(),
            verdict_pattern=pattern,
            predicted_continuation=prediction,
            historical_support=support,
            alignment=align,
            observation_count=historical_check.get("count", 0),
            notes=historical_check.get("similar_patterns", []),
        )

        self.validations.append(val)

        with open(self.vault_path / "pattern_validations.jsonl", "a") as f:
            f.write(json.dumps(asdict(val)) + "\n")

        # Update support stats
        if pattern not in self.pattern_support:
            self.pattern_support[pattern] = {"checks": 0, "supports": 0}
        self.pattern_support[pattern]["checks"] += 1
        if align == "supported":
            self.pattern_support[pattern]["supports"] += 1

        with open(self.vault_path / "pattern_support.json", "w") as f:
            json.dump(self.pattern_support, f)

        return v_id

    def get_stats(self) -> Dict:
        total = len(self.validations)
        if not total:
            return {}
        supported = sum(1 for v in self.validations if v.alignment == "supported")
        return {
            "total_validated": total,
            "historical_support_rate": supported / total,
            "pattern_count": len(self.pattern_support),
        }
