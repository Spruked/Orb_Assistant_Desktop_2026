from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional


class MissionDeniedError(Exception):
    pass


class OrbClass(Enum):
    SCOUT = auto()
    ARCHIVIST = auto()
    ANALYST = auto()
    VERIFIER = auto()
    SENTINEL = auto()
    HERALD = auto()


class MissionType(Enum):
    TOPIC_SURVEY = auto()
    DEEP_INVESTIGATION = auto()
    COMPREHENSIVE_DOSSIER = auto()
    EMERGENCY_RESPONSE = auto()


@dataclass
class ResearchFinding:
    source: str = "unknown"
    title: str = "Untitled"
    confidence: float = 0.5
    payload: Dict[str, Any] = field(default_factory=dict)


@dataclass
class OrbInstance:
    orb_id: str
    orb_class: OrbClass
    lane: str = "general"
    status: str = "queued"


@dataclass
class SwarmMission:
    mission_id: str
    topic: str
    mission_type: MissionType
    context: Dict[str, Any] = field(default_factory=dict)
    active_orbs: Dict[str, OrbInstance] = field(default_factory=dict)
    queued_orbs: List[OrbInstance] = field(default_factory=list)
    created_at: float = field(default_factory=time.time)


class EpistemicSwarmGovernor:
    """Minimal local governor shim used by research orchestrator imports."""

    def __init__(self, backend: Any = None, vault: Any = None):
        self.backend = backend
        self.vault = vault
        self._missions: Dict[str, SwarmMission] = {}
        self._orb_events: Dict[str, Dict[str, Any]] = {}
        self.on_orb_spawn = None
        self.on_orb_return = None
        self.on_mission_complete = None

    async def initiate_mission(
        self, topic: str, mission_type: MissionType, context: Optional[Dict[str, Any]] = None
    ) -> SwarmMission:
        if not str(topic or "").strip():
            raise MissionDeniedError("Topic is required.")

        mission_id = f"mission_{int(time.time() * 1000)}"
        queued = [
            OrbInstance(orb_id=f"{mission_id}_scout", orb_class=OrbClass.SCOUT, lane="discovery"),
            OrbInstance(orb_id=f"{mission_id}_archivist", orb_class=OrbClass.ARCHIVIST, lane="archives"),
            OrbInstance(orb_id=f"{mission_id}_analyst", orb_class=OrbClass.ANALYST, lane="analysis"),
            OrbInstance(orb_id=f"{mission_id}_verifier", orb_class=OrbClass.VERIFIER, lane="verification"),
        ]
        mission = SwarmMission(
            mission_id=mission_id,
            topic=topic,
            mission_type=mission_type,
            context=context or {},
            queued_orbs=queued,
        )
        self._missions[mission_id] = mission
        return mission

    async def process_orb_completion(self, orb_id: str, findings: List[Dict[str, Any]]) -> None:
        self._orb_events[orb_id] = {
            "status": "completed",
            "findings_count": len(findings or []),
            "updated_at": time.time(),
        }
        if callable(self.on_orb_return):
            self.on_orb_return({"orb_id": orb_id, "findings_count": len(findings or [])})

    async def report_orb_failure(self, orb_id: str, error: str, retryable: bool = True) -> None:
        self._orb_events[orb_id] = {
            "status": "failed",
            "error": str(error),
            "retryable": bool(retryable),
            "updated_at": time.time(),
        }

    def get_mission_status(self, mission_id: str) -> Dict[str, Any]:
        mission = self._missions.get(mission_id)
        if not mission:
            return {"mission_id": mission_id, "status": "missing"}

        return {
            "mission_id": mission_id,
            "topic": mission.topic,
            "mission_type": mission.mission_type.name,
            "active_orbs": list(mission.active_orbs.keys()),
            "queued_orbs": [orb.orb_id for orb in mission.queued_orbs],
            "orb_events": self._orb_events,
        }

