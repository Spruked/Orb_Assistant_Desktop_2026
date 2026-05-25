from pathlib import Path
from typing import Any, Dict, List, Optional

from ..substrate.local_substrate import LocalSwarmSubstrate


class OrbSwarmBridge:
    """Utility bridge for sovereign Orb instances sharing local substrate state."""

    def __init__(self, system_root: Path, orb_id: str):
        self.orb_id = str(orb_id or "orb")
        self.substrate = LocalSwarmSubstrate(Path(system_root))

    def check_shared_cache(self, query: str, domains: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        return self.substrate.lookup_research(query=query, domains=domains or [])

    def write_result(
        self, query: str, domains: Optional[List[str]], result: Dict[str, Any]
    ) -> Optional[str]:
        return self.substrate.store_research(query=query, domains=domains or [], result=result or {})

    def publish_task(
        self, payload: Dict[str, Any], capability: str = "general", priority: int = 5
    ) -> Optional[str]:
        task = {
            "publisher_orb": self.orb_id,
            "payload": payload or {},
        }
        return self.substrate.publish_task(task, capability=capability, priority=priority)

    def claim_task(self, capability: str = "general") -> Optional[Dict[str, Any]]:
        return self.substrate.claim_task(worker_id=self.orb_id, capability=capability)

    def complete_task(self, task_id: str, result: Optional[Dict[str, Any]] = None) -> bool:
        final_result = {
            "worker_orb": self.orb_id,
            "result": result or {},
        }
        return self.substrate.complete_task(task_id=task_id, result=final_result)

    def get_status(self) -> Dict[str, Any]:
        return {
            "orb_id": self.orb_id,
            "substrate": self.substrate.get_status(),
        }

