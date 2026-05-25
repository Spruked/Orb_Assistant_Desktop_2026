from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Dict, List


class CALISkill(ABC):
    """Base contract for all CALI domain skills."""

    def __init__(self, skill_id: str, config: Dict[str, Any]):
        self.skill_id = skill_id
        self.config = config
        self.metadata = self._load_metadata()
        self.loaded_at = datetime.utcnow()
        self.active = False
        self.context: Dict[str, Any] = {}

    @abstractmethod
    def _load_metadata(self) -> Dict[str, Any]:
        """Load skill metadata from skill.json configuration."""
        raise NotImplementedError

    @abstractmethod
    def can_handle(self, intent: str, context: Dict[str, Any]) -> float:
        """Return confidence from 0.0 to 1.0 that this skill can handle the request."""
        raise NotImplementedError

    @abstractmethod
    def execute(self, command: str, params: Dict[str, Any], memory: Any) -> Dict[str, Any]:
        """Execute skill-specific logic."""
        raise NotImplementedError

    def get_memory_scope(self) -> List[str]:
        return list(self.config.get("memory_scope") or [f"skills/{self.skill_id}"])

    def activate(self) -> None:
        self.active = True
        self.on_activate()

    def deactivate(self) -> None:
        self.active = False
        self.on_deactivate()

    def on_activate(self) -> None:
        pass

    def on_deactivate(self) -> None:
        pass
