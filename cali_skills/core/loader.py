import importlib.util
import json
import sys
from typing import Dict, Optional

from .interface import CALISkill


class SkillLoader:
    """Hot-loads skills at runtime."""

    def __init__(self, registry):
        self.registry = registry
        self.loaded_skills: Dict[str, CALISkill] = {}
        self.active_skills: Dict[str, CALISkill] = {}

    def load(self, skill_id: str) -> Optional[CALISkill]:
        if skill_id in self.loaded_skills:
            return self.loaded_skills[skill_id]

        skill_path = self.registry.get_skill_path(skill_id)
        if not skill_path:
            return None

        with (skill_path / "skill.json").open("r", encoding="utf-8") as handle:
            config = json.load(handle)

        logic_path = skill_path / "logic.py"
        if not logic_path.exists():
            return None

        module_name = f"cali_runtime_skill_{skill_id}"
        spec = importlib.util.spec_from_file_location(module_name, logic_path)
        if not spec or not spec.loader:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

        skill_class = getattr(module, config["entry_class"])
        skill_instance = skill_class(skill_id, config)
        self.loaded_skills[skill_id] = skill_instance
        return skill_instance

    def activate(self, skill_id: str) -> bool:
        skill = self.load(skill_id)
        if not skill:
            return False
        skill.activate()
        self.active_skills[skill_id] = skill
        return True

    def deactivate(self, skill_id: str) -> None:
        skill = self.active_skills.get(skill_id)
        if skill:
            skill.deactivate()
            del self.active_skills[skill_id]

    def get_active(self) -> Dict[str, CALISkill]:
        return dict(self.active_skills)
