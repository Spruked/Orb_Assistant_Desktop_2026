from cali_skills.core.interface import CALISkill


class FinanceSkill(CALISkill):
    def _load_metadata(self):
        return self.config

    def can_handle(self, intent: str, context: dict) -> float:
        text = str(intent or "").lower()
        return 0.84 if any(trigger in text for trigger in self.config.get("triggers", [])) else 0.04

    def execute(self, command: str, params: dict, memory: object) -> dict:
        if command in {"explain", "route"}:
            return {"status": "success", "result": "Finance skill is available for local accounting, wallet, market, and tax workflow routing once source ledgers are configured.", "confidence": 0.75}
        return {"status": "unknown_command", "confidence": 0.0}
