"""Cognitive state with tracelogging and apriori truth management."""

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
    verdict_type: str
    conclusion: str
    confidence: float
    ethics_alignment_score: float
    was_used: bool
    was_correct: Optional[bool] = None
    validation_timestamp: Optional[float] = None
    context_hash: str = ""


@dataclass
class Syllogism:
    major_premise: str
    minor_premise: str
    conclusion: str
    validity: bool
    certainty: float
    timestamp: float
    ethics_validated: bool = False


@dataclass
class AprioriTruth:
    statement: str
    certainty: float
    validation_count: int
    first_observed: float
    last_confirmed: float
    ethical_implications: Dict[str, float]


class DeductiveCognition:
    def __init__(self, vault_path: Path):
        self.vault_path = vault_path
        self.vault_path.mkdir(parents=True, exist_ok=True)

        # Standard paths
        self.apriori_path = self.vault_path / "apriori"
        self.apriori_path.mkdir(exist_ok=True)
        self.trace_path = self.vault_path / "trace"
        self.trace_path.mkdir(exist_ok=True)

        # State containers
        self.syllogism_chain: List[Syllogism] = []
        self.premise_base: Dict[str, Dict] = {}
        self.verdict_tracelog: deque = deque(
            maxlen=1000
        )  # Circular buffer for recent traces
        self.apriori_truths: Dict[str, AprioriTruth] = {}

        # Calibration data
        self.confidence_calibration = {
            "total_verdicts": 0,
            "correct_verdicts": 0,
            "confidence_accuracy": 1.0,  # How often confidence matches reality
        }

        self._load_all()

    def _load_all(self):
        """Load apriori truths and recent tracelog."""
        # Load apriori truths
        apriori_file = self.apriori_path / "absolute_truths.json"
        if apriori_file.exists():
            with open(apriori_file, "r") as f:
                data = json.load(f)
                self.apriori_truths = {k: AprioriTruth(**v) for k, v in data.items()}

        # Load tracelog (last 1000)
        trace_file = self.trace_path / "verdict_log.jsonl"
        if trace_file.exists():
            with open(trace_file, "r") as f:
                lines = f.readlines()[-1000:]
                for line in lines:
                    try:
                        data = json.loads(line)
                        self.verdict_tracelog.append(VerdictTrace(**data))
                    except:
                        continue

        # Load calibration
        cal_file = self.vault_path / "calibration.json"
        if cal_file.exists():
            with open(cal_file, "r") as f:
                self.confidence_calibration = json.load(f)

        # Load premises
        state_file = self.vault_path / "deductive_state.json"
        if state_file.exists():
            with open(state_file, "r") as f:
                data = json.load(f)
                self.premise_base = data.get("premises", {})
                self.syllogism_chain = [Syllogism(**s) for s in data.get("chain", [])]

    def save_apriori(self):
        """Save absolute truths separately."""
        apriori_file = self.apriori_path / "absolute_truths.json"
        with open(apriori_file, "w") as f:
            json.dump(
                {k: asdict(v) for k, v in self.apriori_truths.items()}, f, indent=2
            )

    def save_tracelog(self):
        """Append-only tracelog for recursive processing."""
        trace_file = self.trace_path / "verdict_log.jsonl"
        # Save only new entries
        with open(trace_file, "a") as f:
            for trace in self.verdict_tracelog:
                if not hasattr(trace, "_written"):
                    f.write(json.dumps(asdict(trace)) + "\n")
                    trace._written = True

    def save_state(self):
        """Save mutable state."""
        state_file = self.vault_path / "deductive_state.json"
        with open(state_file, "w") as f:
            json.dump(
                {
                    "premises": self.premise_base,
                    "chain": [asdict(s) for s in self.syllogism_chain],
                    "calibration": self.confidence_calibration,
                    "last_updated": time.time(),
                },
                f,
                indent=2,
            )
        self.save_apriori()

    def record_verdict(self, verdict_data: Dict, context: Dict) -> str:
        """
        Record verdict to tracelog with ethics alignment scoring.
        Returns verdict_id for tracking.
        """
        # Generate deterministic ID from content
        content_str = json.dumps(verdict_data, sort_keys=True)
        verdict_id = hashlib.sha256(f"{content_str}{time.time()}".encode()).hexdigest()[
            :16
        ]

        # Calculate ethics alignment (deterministic based on validity and certainty)
        ethics_score = self._calculate_ethics_alignment(verdict_data)

        trace = VerdictTrace(
            verdict_id=verdict_id,
            timestamp=time.time(),
            verdict_type=verdict_data.get("verdict", "unknown"),
            conclusion=str(verdict_data.get("conclusion", "")),
            confidence=verdict_data.get("certainty", 0.0),
            ethics_alignment_score=ethics_score,
            was_used=False,
            context_hash=hashlib.sha256(
                json.dumps(context, sort_keys=True).encode()
            ).hexdigest()[:8],
        )

        self.verdict_tracelog.append(trace)
        self.confidence_calibration["total_verdicts"] += 1
        self.save_tracelog()

        return verdict_id

    def mark_verdict_used(self, verdict_id: str, was_correct: bool):
        """Called by ORB/validator when verdict is used and validated."""
        for trace in self.verdict_tracelog:
            if trace.verdict_id == verdict_id:
                trace.was_used = True
                trace.was_correct = was_correct
                trace.validation_timestamp = time.time()

                if was_correct:
                    self.confidence_calibration["correct_verdicts"] += 1
                    # Promote to apriori if consistently correct
                    self._consider_apriori_promotion(trace)

                self._update_calibration()
                self.save_tracelog()
                break

    def _consider_apriori_promotion(self, trace: VerdictTrace):
        """Move highly validated truths to apriori storage."""
        if trace.confidence > 0.95 and trace.ethics_alignment_score > 0.9:
            truth_key = f"{trace.verdict_type}:{trace.conclusion}"

            if truth_key in self.apriori_truths:
                # Strengthen existing
                truth = self.apriori_truths[truth_key]
                truth.validation_count += 1
                truth.last_confirmed = time.time()
                truth.certainty = min(0.999, truth.certainty + 0.001)
            else:
                # New absolute truth
                self.apriori_truths[truth_key] = AprioriTruth(
                    statement=trace.conclusion,
                    certainty=trace.confidence,
                    validation_count=1,
                    first_observed=trace.timestamp,
                    last_confirmed=time.time(),
                    ethical_implications={"validity": trace.ethics_alignment_score},
                )

            self.save_apriori()

    def _calculate_ethics_alignment(self, verdict_data: Dict) -> float:
        """
        Deterministic ethics calculation:
        - Valid deduction: +0.4
        - High certainty: +0.3
        - Consistent with premises: +0.3
        """
        score = 0.0
        if verdict_data.get("valid"):
            score += 0.4
        certainty = verdict_data.get("certainty", 0)
        score += certainty * 0.3
        if verdict_data.get("chain_consistency"):
            score += 0.3
        return min(score, 1.0)

    def _update_calibration(self):
        """Update confidence accuracy metrics."""
        total = self.confidence_calibration["total_verdicts"]
        if total > 0:
            accuracy = self.confidence_calibration["correct_verdicts"] / total
            self.confidence_calibration["confidence_accuracy"] = accuracy

    def idle_recursive_process(self) -> Dict[str, Any]:
        """
        Called by CALI during idle cycles to improve future verdicts.
        Analyzes tracelog patterns and adjusts confidence calculations.
        """
        if len(self.verdict_tracelog) < 10:
            return {"processed": 0, "improvements": []}

        improvements = []

        # Pattern analysis: which premise types lead to correct verdicts?
        premise_success = {}
        for trace in self.verdict_tracelog:
            if trace.was_correct is not None:
                # Extract premise context from tracelog (simplified)
                key = trace.verdict_type
                if key not in premise_success:
                    premise_success[key] = {"correct": 0, "total": 0}
                premise_success[key]["total"] += 1
                if trace.was_correct:
                    premise_success[key]["correct"] += 1

        # Adjust premise weights based on historical accuracy
        for premise_type, stats in premise_success.items():
            if stats["total"] > 5:
                accuracy = stats["correct"] / stats["total"]
                if accuracy < 0.5 and premise_type in self.premise_base:
                    # Reduce weight of unreliable premises
                    self.premise_base[premise_type]["reliability"] = accuracy
                    improvements.append(
                        f"Adjusted {premise_type} reliability to {accuracy:.2f}"
                    )

        # Update calibration
        self._update_calibration()
        self.save_state()

        return {
            "processed": len(self.verdict_tracelog),
            "improvements": improvements,
            "calibration": self.confidence_calibration,
            "apriori_count": len(self.apriori_truths),
        }

    def query_apriori(self, query_type: str) -> List[AprioriTruth]:
        """Provide CALI with absolute truths for discernment."""
        return [
            truth
            for key, truth in self.apriori_truths.items()
            if query_type in key and truth.certainty > 0.9
        ]

    def add_premise(self, category: str, rule: Dict):
        self.premise_base[category] = {
            "rule": rule,
            "added": time.time(),
            "uses": 0,
            "reliability": 1.0,  # Start optimistic
        }
        self.save_state()

    def record_syllogism(
        self, major: str, minor: str, conclusion: str, valid: bool, certainty: float
    ):
        syllogism = Syllogism(
            major_premise=major,
            minor_premise=minor,
            conclusion=conclusion,
            validity=valid,
            certainty=certainty,
            timestamp=time.time(),
            ethics_validated=(certainty > 0.9 and valid),
        )
        self.syllogism_chain.append(syllogism)
        for premise in [major, minor]:
            for cat, data in self.premise_base.items():
                if premise in str(data.get("rule", {})):
                    data["uses"] += 1
        self.save_state()

    def get_premise(self, category: str) -> Optional[Dict]:
        return self.premise_base.get(category)

    def get_last_n_syllogisms(self, n: int = 5) -> List[Syllogism]:
        return self.syllogism_chain[-n:] if self.syllogism_chain else []

    def calculate_validity_score(self) -> float:
        if not self.syllogism_chain:
            return 0.0
        valid_count = sum(1 for s in self.syllogism_chain if s.validity)
        return valid_count / len(self.syllogism_chain)

    def get_calibration_report(self) -> Dict:
        """Export calibration data for CALI."""
        return {
            **self.confidence_calibration,
            "apriori_truths_count": len(self.apriori_truths),
            "recent_verdicts": len(self.verdict_tracelog),
            "premise_reliabilities": {
                k: v.get("reliability", 1.0) for k, v in self.premise_base.items()
            },
        }
