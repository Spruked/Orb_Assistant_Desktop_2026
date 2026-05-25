import json
from pathlib import Path

from cali_skills.core.interface import CALISkill


class SprukedSkill(CALISkill):
    def _load_metadata(self):
        return self.config

    def can_handle(self, intent: str, context: dict) -> float:
        text = str(intent or "").lower()
        return 0.88 if any(trigger in text for trigger in self.config.get("triggers", [])) else 0.05

    def _core_path(self):
        return Path(__file__).resolve().parents[3] / "CALI_System" / "core_knowledge" / "spruked"

    def execute(self, command: str, params: dict, memory: object) -> dict:
        core_path = self._core_path()
        if command in {"explain", "describe"}:
            overview = (core_path / "overview.txt").read_text(encoding="utf-8", errors="replace") if (core_path / "overview.txt").exists() else ""
            return {"status": "success", "result": overview.strip(), "confidence": 0.88}
        if command == "list_sites":
            sites_path = core_path / "sites.json"
            sites = json.loads(sites_path.read_text(encoding="utf-8")) if sites_path.exists() else {"sites": []}
            return {"status": "success", "result": sites, "confidence": 0.88}
        return {"status": "unknown_command", "confidence": 0.0}
