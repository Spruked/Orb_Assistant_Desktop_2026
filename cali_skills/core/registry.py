import json
from pathlib import Path
from typing import Dict, List, Optional


class SkillRegistry:
    """Discovers and catalogs available CALI skills."""

    def __init__(self, library_path: str = "cali_skills/library"):
        self.library_path = Path(library_path).expanduser().resolve()
        self.catalog: Dict[str, Dict] = {}
        self._scan_library()

    def _scan_library(self) -> None:
        self.catalog = {}
        if not self.library_path.exists():
            return

        for skill_dir in self.library_path.iterdir():
            if not skill_dir.is_dir():
                continue
            skill_json = skill_dir / "skill.json"
            logic_py = skill_dir / "logic.py"
            if not skill_json.exists() or not logic_py.exists():
                continue
            with skill_json.open("r", encoding="utf-8") as handle:
                config = json.load(handle)
            skill_id = config.get("skill_id")
            if not skill_id:
                continue
            self.catalog[skill_id] = {
                "path": skill_dir,
                "config": config,
                "status": "available",
            }

    def refresh(self) -> None:
        self._scan_library()

    def list_skills(self, category: Optional[str] = None) -> List[Dict]:
        skills = []
        for skill_id, info in sorted(self.catalog.items()):
            config = info["config"]
            if category is not None and config.get("category") != category:
                continue
            skills.append(
                {
                    "id": skill_id,
                    "name": config.get("name", skill_id),
                    "version": config.get("version", "0.0.0"),
                    "description": config.get("description", ""),
                    "triggers": config.get("triggers", []),
                    "status": info.get("status", "available"),
                }
            )
        return skills

    def get_skill_path(self, skill_id: str) -> Optional[Path]:
        info = self.catalog.get(skill_id)
        return info["path"] if info else None

    def get_config(self, skill_id: str) -> Optional[Dict]:
        info = self.catalog.get(skill_id)
        return info["config"] if info else None
