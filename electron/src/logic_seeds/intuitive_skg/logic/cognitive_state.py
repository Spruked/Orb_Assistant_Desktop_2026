import json
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, asdict, field
from collections import deque


@dataclass
class NecessityVerdict:
    verdict_id: str
    timestamp: float
    symmetry_score: float
    density: int
    certainty: float
    vector: Tuple[float, float]
    bypass_depth: int
    ethics_alignment: float
    validated: Optional[bool] = None
    validation_time: Optional[float] = None


@dataclass
class AprioriNecessity:
    condition_hash: str  # Hash of density+symmetry thresholds
    unity_vector: Tuple[float, float]
    validation_count: int
    average_certainty: float
    ethics_score: float


class IntuitiveCognition:
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.vault_path.mkdir(parents=True, exist_ok=True)

        # Existing intuitive state (placeholders)
        self.unity_threshold = 0.9

        # New additions
        self.apriori_path = self.vault_path / "apriori"
        self.apriori_path.mkdir(exist_ok=True)
        self.trace_path = self.vault_path / "trace"
        self.trace_path.mkdir(exist_ok=True)

        self.necessity_tracelog: deque = deque(maxlen=1000)
        self.apriori_necessities: Dict[str, AprioriNecessity] = {}

        # Track field state accuracy
        self.field_predictions: List[Dict] = []

        self._load_all()

    def _load_all(self):
        # Load apriori necessities
        ap_file = self.apriori_path / "unity_conditions.json"
        if ap_file.exists():
            with open(ap_file, "r") as f:
                data = json.load(f)
                self.apriori_necessities = {
                    k: AprioriNecessity(**v) for k, v in data.items()
                }

        # Load tracelog
        trace_file = self.trace_path / "necessity_log.jsonl"
        if trace_file.exists():
            with open(trace_file, "r") as f:
                for line in f.readlines()[-1000:]:
                    try:
                        self.necessity_tracelog.append(
                            NecessityVerdict(**json.loads(line))
                        )
                    except:
                        continue

    def record_necessity_verdict(self, necessity_data: Dict, context: Dict) -> str:
        """Record intuitive jump verdict."""
        verdict_id = hashlib.sha256(
            f"{necessity_data['density']}{necessity_data['symmetry']}{time.time()}".encode()
        ).hexdigest()[:16]

        # Ethics: unity promotes coherence (high ethics)
        ethics_score = 0.3 + (0.7 * necessity_data.get("symmetry", 0))

        verdict = NecessityVerdict(
            verdict_id=verdict_id,
            timestamp=time.time(),
            symmetry_score=necessity_data["symmetry"],
            density=necessity_data["density"],
            certainty=necessity_data["certainty"],
            vector=necessity_data["vector"],
            bypass_depth=necessity_data["bypass_depth"],
            ethics_alignment=ethics_score,
        )

        self.necessity_tracelog.append(verdict)

        with open(self.trace_path / "necessity_log.jsonl", "a") as f:
            f.write(json.dumps(asdict(verdict)) + "\n")

        return verdict_id

    def validate_necessity(self, verdict_id: str, was_optimal: bool):
        """Check if the jump was actually optimal (saved time/resources)."""
        for verdict in self.necessity_tracelog:
            if verdict.verdict_id == verdict_id:
                verdict.validated = was_optimal
                verdict.validation_time = time.time()

                if was_optimal:
                    # Create condition hash
                    cond_hash = f"d{verdict.density}_s{int(verdict.symmetry_score*100)}"

                    if cond_hash in self.apriori_necessities:
                        ap = self.apriori_necessities[cond_hash]
                        ap.validation_count += 1
                        ap.average_certainty = (
                            ap.average_certainty * (ap.validation_count - 1)
                            + verdict.certainty
                        ) / ap.validation_count
                    else:
                        self.apriori_necessities[cond_hash] = AprioriNecessity(
                            condition_hash=cond_hash,
                            unity_vector=verdict.vector,
                            validation_count=1,
                            average_certainty=verdict.certainty,
                            ethics_score=verdict.ethics_alignment,
                        )

                    self._save_apriori()
                break

    def _save_apriori(self):
        with open(self.apriori_path / "unity_conditions.json", "w") as f:
            json.dump({k: asdict(v) for k, v in self.apriori_necessities.items()}, f)

    def idle_recursive_process(self) -> Dict:
        """Refine symmetry thresholds based on validation."""
        if len(self.necessity_tracelog) < 10:
            return {"processed": 0}

        # Analyze which threshold combinations lead to valid jumps
        valid_jumps = [v for v in self.necessity_tracelog if v.validated]
        invalid_jumps = [v for v in self.necessity_tracelog if v.validated == False]

        improvements = []

        if valid_jumps and invalid_jumps:
            avg_sym_valid = sum(v.symmetry_score for v in valid_jumps) / len(
                valid_jumps
            )
            avg_sym_invalid = sum(v.symmetry_score for v in invalid_jumps) / len(
                invalid_jumps
            )

            if avg_sym_valid > avg_sym_invalid:
                # Increase threshold slightly toward valid mean
                new_threshold = (self.unity_threshold + avg_sym_valid) / 2
                if abs(new_threshold - self.unity_threshold) > 0.05:
                    self.unity_threshold = new_threshold
                    improvements.append(
                        f"Adjusted symmetry threshold to {new_threshold:.3f}"
                    )

        return {
            "processed": len(self.necessity_tracelog),
            "valid_jumps": len(valid_jumps),
            "improvements": improvements,
            "apriori_conditions": len(self.apriori_necessities),
        }

    def query_apriori(
        self, density_range: Tuple[int, int] = None
    ) -> List[AprioriNecessity]:
        """Supply CALI with validated unity conditions."""
        result = list(self.apriori_necessities.values())
        if density_range:
            # Filter by parsing condition_hash
            filtered = []
            for ap in result:
                try:
                    d = int(ap.condition_hash.split("_")[0][1:])
                    if density_range[0] <= d <= density_range[1]:
                        filtered.append(ap)
                except:
                    continue
            return filtered
        return result
