from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class SkillContext:
    intent: str
    current_app: Optional[str] = None
    topic: Optional[str] = None
    user_tier: Optional[str] = None
    memory: Any = None
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat() + "Z")

    def as_dict(self) -> Dict[str, Any]:
        return {
            "intent": self.intent,
            "current_app": self.current_app,
            "topic": self.topic,
            "user_tier": self.user_tier,
            "memory": self.memory,
            "metadata": self.metadata,
            "created_at": self.created_at,
        }
