import json
import time
import hashlib
from pathlib import Path
from typing import List, Dict, Optional, Tuple, Any
from dataclasses import dataclass, asdict, field
from collections import deque


@dataclass
class VerdictTrace:
    verdict_id: str
    timestamp: float
    pattern_predicted: str
    confidence: float
    actual_outcome: Optional[str] = None
    was_correct: Optional[bool] = None
    ethics_alignment: float = 0.0  # Based on consistency with established patterns
    vivacity_at_time: float = 0.0
    validation_time: Optional[float] = None


@dataclass
class AprioriPattern:
    pattern_key: str
    frequency: float
    predictive_accuracy: float
    ethics_score: float
    validated_count: int
    first_seen: float


class InductiveCognition:
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.vault_path.mkdir(parents=True, exist_ok=True)

        # Existing inductive state (placeholders)
        self.conjunction_memory = {}
        self.vivacity_threshold = 0.5

        # New additions
        self.apriori_path = self.vault_path / "apriori"
        self.apriori_path.mkdir(exist_ok=True)
        self.trace_path = self.vault_path / "trace"
        self.trace_path.mkdir(exist_ok=True)

        self.verdict_tracelog: deque = deque(maxlen=1000)
        self.apriori_patterns: Dict[str, AprioriPattern] = {}

        # Accuracy tracking per pattern type
        self.pattern_accuracy: Dict[str, Dict] = {}

        self._load_all()

    def _load_all(self):
        # Load apriori patterns
        apriori_file = self.apriori_path / "validated_patterns.json"
        if apriori_file.exists():
            with open(apriori_file, "r") as f:
                data = json.load(f)
                self.apriori_patterns = {
                    k: AprioriPattern(**v) for k, v in data.items()
                }

        # Load tracelog
        trace_file = self.trace_path / "verdict_log.jsonl"
        if trace_file.exists():
            with open(trace_file, "r") as f:
                for line in f.readlines()[-1000:]:
                    try:
                        self.verdict_tracelog.append(VerdictTrace(**json.loads(line)))
                    except:
                        continue

        # Load accuracy tracking
        acc_file = self.vault_path / "pattern_accuracy.json"
        if acc_file.exists():
            with open(acc_file, "r") as f:
                self.pattern_accuracy = json.load(f)

    def record_verdict(self, prediction: Dict, context: Dict) -> str:
        """Record inductive verdict before outcome is known."""
        verdict_id = hashlib.sha256(
            f"{prediction['pattern']}{time.time()}".encode()
        ).hexdigest()[:16]

        # Ethics alignment: consistency with apriori patterns
        ethics_score = self._calculate_ethics_alignment(prediction)

        trace = VerdictTrace(
            verdict_id=verdict_id,
            timestamp=time.time(),
            pattern_predicted=prediction["pattern"],
            confidence=prediction["confidence"],
            ethics_alignment=ethics_score,
            vivacity_at_time=prediction.get("vivacity", 0),
        )

        self.verdict_tracelog.append(trace)

        # Save immediately
        with open(self.trace_path / "verdict_log.jsonl", "a") as f:
            f.write(json.dumps(asdict(trace)) + "\n")

        return verdict_id

    def validate_verdict(self, verdict_id: str, actual_outcome: str):
        """Update trace with actual outcome."""
        for trace in self.verdict_tracelog:
            if trace.verdict_id == verdict_id:
                trace.actual_outcome = actual_outcome
                trace.was_correct = actual_outcome == trace.pattern_predicted
                trace.validation_time = time.time()

                # Update pattern accuracy
                pattern = trace.pattern_predicted
                if pattern not in self.pattern_accuracy:
                    self.pattern_accuracy[pattern] = {"correct": 0, "total": 0}

                self.pattern_accuracy[pattern]["total"] += 1
                if trace.was_correct:
                    self.pattern_accuracy[pattern]["correct"] += 1
                    self._promote_to_apriori(pattern, trace)

                self._save_accuracy()
                break

    def _promote_to_apriori(self, pattern: str, trace: VerdictTrace):
        """Move frequently correct patterns to apriori."""
        stats = self.pattern_accuracy[pattern]
        if stats["total"] >= 5 and (stats["correct"] / stats["total"]) > 0.8:
            if pattern in self.conjunction_memory:
                conj = self.conjunction_memory[pattern]

                self.apriori_patterns[pattern] = AprioriPattern(
                    pattern_key=pattern,
                    frequency=conj.frequency,
                    predictive_accuracy=stats["correct"] / stats["total"],
                    ethics_score=trace.ethics_alignment,
                    validated_count=stats["correct"],
                    first_seen=conj.last_observed - (conj.observations * 3600),
                )

                # Save apriori
                with open(self.apriori_path / "validated_patterns.json", "w") as f:
                    json.dump(
                        {k: asdict(v) for k, v in self.apriori_patterns.items()}, f
                    )

    def _calculate_ethics_alignment(self, prediction: Dict) -> float:
        """
        Ethics for induction:
        - High consistency with history: +0.5
        - Moderate confidence (not overconfident): +0.3
        - Pattern simplicity (Occam's razor): +0.2
        """
        score = 0.0

        # Check against apriori
        pattern = prediction["pattern"]
        if pattern in self.apriori_patterns:
            ap = self.apriori_patterns[pattern]
            score += ap.predictive_accuracy * 0.5

        confidence = prediction.get("confidence", 0)
        if 0.4 <= confidence <= 0.8:  # Sweet spot - not over/under confident
            score += 0.3

        # Simplicity bonus (shorter patterns preferred)
        pattern_length = len(pattern.split("→"))
        score += max(0, (5 - pattern_length) * 0.04)

        return min(score, 1.0)

    def idle_recursive_process(self) -> Dict:
        """Improve confidence calculations based on historical accuracy."""
        if len(self.verdict_tracelog) < 20:
            return {"processed": 0}

        improvements = []

        # Adjust confidence thresholds based on actual accuracy
        correct_high_conf = [
            t for t in self.verdict_tracelog if t.was_correct and t.confidence > 0.5
        ]
        wrong_high_conf = [
            t for t in self.verdict_tracelog if not t.was_correct and t.confidence > 0.5
        ]

        if len(wrong_high_conf) > len(correct_high_conf) * 0.3:
            # We're overconfident - adjust vivacity scaling
            self.vivacity_threshold = min(1.0, self.vivacity_threshold * 1.1)
            improvements.append("Reduced confidence bias (overconfidence detected)")

        # Promote strong patterns to premise-like status
        for pattern, stats in self.pattern_accuracy.items():
            if stats["total"] > 10 and (stats["correct"] / stats["total"]) > 0.85:
                if pattern not in self.apriori_patterns:
                    self._promote_to_apriori(
                        pattern,
                        next(
                            t
                            for t in self.verdict_tracelog
                            if t.pattern_predicted == pattern
                        ),
                    )
                    improvements.append(f"Promoted {pattern} to apriori")

        return {
            "processed": len(self.verdict_tracelog),
            "improvements": improvements,
            "apriori_patterns": len(self.apriori_patterns),
            "accuracy_rates": {
                k: v["correct"] / v["total"]
                for k, v in self.pattern_accuracy.items()
                if v["total"] > 0
            },
        }

    def query_apriori(self, query_pattern: str = None) -> List[AprioriPattern]:
        """Supply CALI with validated patterns."""
        if query_pattern:
            return [p for k, p in self.apriori_patterns.items() if query_pattern in k]
        return list(self.apriori_patterns.values())

    def _save_accuracy(self):
        with open(self.vault_path / "pattern_accuracy.json", "w") as f:
            json.dump(self.pattern_accuracy, f)
