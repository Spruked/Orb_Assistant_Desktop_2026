from cali_skills.core.interface import CALISkill


class CodeSkill(CALISkill):
    def _load_metadata(self):
        return self.config

    def can_handle(self, intent: str, context: dict) -> float:
        text = str(intent or "").lower()
        return 0.84 if any(trigger in text for trigger in self.config.get("triggers", [])) else 0.04

    def execute(self, command: str, params: dict, memory: object) -> dict:
        return {
            "status": "success" if command in {"explain", "route"} else "unknown_command",
            "result": "Code skill is available for local repo analysis and development routing.",
            "confidence": 0.75 if command in {"explain", "route"} else 0.0,
        }
