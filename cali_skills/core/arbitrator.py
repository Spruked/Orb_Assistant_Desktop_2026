import json
import math
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List


class SkillArbitrator:
    """Ranks active skills and executes the strongest match."""

    def __init__(self, loader):
        self.loader = loader
        self.decisions_path = Path(__file__).resolve().parents[2] / "CALI_System" / "memory" / "decisions.jsonl"

    def select_skill(self, intent: str, context: Dict[str, Any]) -> List[Dict]:
        scores = []
        for skill_id, skill in self.loader.get_active().items():
            confidence = float(skill.can_handle(intent, context))
            if confidence > 0.3:
                scores.append({"skill_id": skill_id, "skill": skill, "confidence": confidence})

        if not scores:
            return []

        max_confidence = max(item["confidence"] for item in scores)
        exp_scores = [math.exp(item["confidence"] - max_confidence) for item in scores]
        total = sum(exp_scores) or 1.0
        for item, exp_score in zip(scores, exp_scores):
            item["softmax_weight"] = float(exp_score / total)
        return sorted(scores, key=lambda item: item["softmax_weight"], reverse=True)

    def execute_best(
        self,
        intent: str,
        command: str,
        params: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        ranked = self.select_skill(intent, context)
        if not ranked:
            result = {"status": "no_skill", "error": "No skill available for intent"}
            self._record_decision(intent, command, [], result)
            return result
        top = ranked[0]
        runtime_context = dict(context or {})
        runtime_context["skills"] = self.loader.get_active()
        result = top["skill"].execute(command, params, runtime_context)
        result.setdefault("skill_id", top["skill_id"])
        result.setdefault("confidence", top["confidence"])
        result["arbitration"] = {
            "selected": top["skill_id"],
            "softmax_weight": top["softmax_weight"],
            "candidates": [
                {"skill_id": item["skill_id"], "confidence": item["confidence"]}
                for item in ranked
            ],
        }
        self._record_decision(intent, command, ranked, result)
        return result

    def _record_decision(self, intent: str, command: str, ranked: List[Dict], result: Dict[str, Any]) -> None:
        self.decisions_path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "id": str(uuid.uuid4()),
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "intent": intent,
            "command": command,
            "selected_skill": ranked[0]["skill_id"] if ranked else None,
            "candidates": [
                {
                    "skill_id": item["skill_id"],
                    "confidence": item["confidence"],
                    "softmax_weight": item.get("softmax_weight"),
                }
                for item in ranked
            ],
            "status": result.get("status"),
            "result_confidence": result.get("confidence"),
            "error": result.get("error"),
        }
        with self.decisions_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=True) + "\n")
