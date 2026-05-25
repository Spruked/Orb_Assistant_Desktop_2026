"""Immutable observation records of validation checks."""

import json
import time
import hashlib
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict
from collections import deque


@dataclass
class ValidationObservation:
    observation_id: str
    timestamp: float
    original_verdict_hash: str
    original_conclusion: str
    deductive_check_result: str
    alignment_status: str  # "congruent", "discrepant", "novel"
    confidence_delta: float
    notes: List[str]
    documented: bool = True


class ValidationCognition:
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.vault_path.mkdir(parents=True, exist_ok=True)

        # Observation log - immutable append-only
        self.observation_log: deque = deque(maxlen=5000)
        self.congruence_patterns: Dict[str, int] = {}

        self._load_log()

    def _load_log(self):
        log_file = self.vault_path / "observation_log.jsonl"
        if log_file.exists():
            with open(log_file, "r") as f:
                for line in list(f)[-5000:]:
                    try:
                        data = json.loads(line)
                        self.observation_log.append(ValidationObservation(**data))
                    except:
                        continue

    def record_observation(self, original_verdict: Dict, check_result: Dict) -> str:
        """Document the validation check without modifying verdict."""
        content = json.dumps(original_verdict, sort_keys=True)
        v_hash = hashlib.sha256(content.encode()).hexdigest()[:12]

        # Determine alignment
        orig_conf = original_verdict.get("confidence", 0)
        check_conf = check_result.get("calculated_confidence", 0)
        delta = abs(orig_conf - check_conf)

        if delta < 0.1:
            status = "congruent"
            self.congruence_patterns[v_hash[:8]] = (
                self.congruence_patterns.get(v_hash[:8], 0) + 1
            )
        elif delta < 0.3:
            status = "variance_noted"
        else:
            status = "discrepant"

        obs = ValidationObservation(
            observation_id=f"obs_{int(time.time()*1000)}",
            timestamp=time.time(),
            original_verdict_hash=v_hash,
            original_conclusion=str(original_verdict.get("conclusion", "")),
            deductive_check_result=check_result.get("check_status", ""),
            alignment_status=status,
            confidence_delta=delta,
            notes=check_result.get("reasoning_chain", []),
        )

        self.observation_log.append(obs)

        # Append to immutable log
        with open(self.vault_path / "observation_log.jsonl", "a") as f:
            f.write(json.dumps(asdict(obs)) + "\n")

        return obs.observation_id

    def get_validation_stats(self) -> Dict:
        """Stats for CALI analysis."""
        total = len(self.observation_log)
        if total == 0:
            return {"total_checks": 0}

        congruent = sum(
            1 for o in self.observation_log if o.alignment_status == "congruent"
        )
        discrepant = sum(
            1 for o in self.observation_log if o.alignment_status == "discrepant"
        )

        return {
            "total_checks": total,
            "congruent_ratio": congruent / total,
            "discrepant_ratio": discrepant / total,
            "avg_confidence_delta": sum(
                o.confidence_delta for o in self.observation_log
            )
            / total,
            "common_patterns": sorted(
                self.congruence_patterns.items(), key=lambda x: x[1], reverse=True
            )[:5],
        }

    def export_recent_observations(self, n: int = 100) -> List[Dict]:
        """Supply CALI with recent validation data."""
        return [asdict(o) for o in list(self.observation_log)[-n:]]
