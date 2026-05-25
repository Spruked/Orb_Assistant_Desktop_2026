from cali_skills.core.interface import CALISkill


class LegalSkill(CALISkill):
    def _load_metadata(self):
        return self.config

    def can_handle(self, intent: str, context: dict) -> float:
        text = str(intent or "").lower()
        return 0.82 if any(trigger in text for trigger in self.config.get("triggers", [])) else 0.04

    def execute(self, command: str, params: dict, memory: object) -> dict:
        if command in {"explain", "route"}:
            return {"status": "success", "result": "Legal skill routes contract, IP, licensing, and compliance work to curated local templates and operator-approved records.", "confidence": 0.74}
        return {"status": "unknown_command", "confidence": 0.0}
