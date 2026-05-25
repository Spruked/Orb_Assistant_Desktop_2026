import json
import queue
import threading
import time
from pathlib import Path
from typing import Any, Dict, Optional

from .substrate.local_substrate import LocalSwarmSubstrate


class CaliSwarmExtensionRuntime:
    """
    Non-blocking runtime bridge for CALI-Swarm extension.
    Designed to be optional and fail-open in live orb IPC runtime.
    """

    def __init__(self, controller=None, system_root: Optional[Path] = None):
        self.controller = controller
        self.system_root = Path(system_root or ".").expanduser().resolve()
        self.events_dir = self.system_root / "swarm"
        self.events_file = self.events_dir / "stimulus_events.jsonl"
        self.events_dir.mkdir(parents=True, exist_ok=True)
        self.substrate = LocalSwarmSubstrate(self.system_root)

        self.running = False
        self._stop_event = threading.Event()
        self._worker = None
        self._q: queue.Queue = queue.Queue(maxsize=1024)

        self._swarm_modules_ready = False
        self._research_modules_ready = False
        self._last_error = None
        self._events_written = 0

    def start_background(self):
        if self.running:
            return
        self.running = True
        self._stop_event.clear()
        self._worker = threading.Thread(
            target=self._run_loop, name="CaliSwarmRuntime", daemon=True
        )
        self._worker.start()

    def _run_loop(self):
        self._load_optional_modules()
        while not self._stop_event.is_set():
            try:
                payload = self._q.get(timeout=0.5)
            except queue.Empty:
                continue
            try:
                with self.events_file.open("a", encoding="utf-8") as f:
                    f.write(json.dumps(payload, default=str) + "\n")
                self._events_written += 1
            except Exception as exc:
                self._last_error = str(exc)

    def _load_optional_modules(self):
        self._swarm_modules_ready = True
        try:
            # Optional load check only; runtime remains operational even if unavailable.
            from .research.swarm_research_orchestrator import SwarmResearchOrchestrator  # noqa: F401

            self._research_modules_ready = True
        except Exception as exc:
            self._research_modules_ready = False
            self._last_error = str(exc)

    def lookup_cached_research(self, query: str, domains: Optional[list] = None) -> Optional[Dict[str, Any]]:
        try:
            return self.substrate.lookup_research(query, domains or [])
        except Exception as exc:
            self._last_error = str(exc)
            return None

    def store_research_result(
        self, query: str, domains: Optional[list], result: Dict[str, Any]
    ) -> Optional[str]:
        try:
            return self.substrate.store_research(query, domains or [], result or {})
        except Exception as exc:
            self._last_error = str(exc)
            return None

    def publish_task(
        self, payload: Dict[str, Any], capability: str = "general", priority: int = 5
    ) -> Optional[str]:
        try:
            return self.substrate.publish_task(payload, capability=capability, priority=priority)
        except Exception as exc:
            self._last_error = str(exc)
            return None

    def claim_task(self, worker_id: str, capability: str = "general") -> Optional[Dict[str, Any]]:
        try:
            return self.substrate.claim_task(worker_id=worker_id, capability=capability)
        except Exception as exc:
            self._last_error = str(exc)
            return None

    def complete_task(self, task_id: str, result: Optional[Dict[str, Any]] = None) -> bool:
        try:
            return self.substrate.complete_task(task_id=task_id, result=result)
        except Exception as exc:
            self._last_error = str(exc)
            return False

    def ingest_stimulus(self, stimulus: Dict[str, Any], thought: Any = None):
        if not self.running:
            return
        thought_data = None
        if thought is not None:
            if hasattr(thought, "pulse"):
                try:
                    thought_data = thought.pulse()
                except Exception:
                    thought_data = str(thought)
            else:
                thought_data = thought

        payload = {
            "timestamp": time.time(),
            "stimulus": stimulus,
            "thought": thought_data,
        }

        try:
            self._q.put_nowait(payload)
        except queue.Full:
            try:
                _ = self._q.get_nowait()
                self._q.put_nowait(payload)
            except Exception:
                pass

    def get_status(self) -> Dict[str, Any]:
        substrate_status = {}
        try:
            substrate_status = self.substrate.get_status()
        except Exception as exc:
            self._last_error = str(exc)
            substrate_status = {"error": str(exc)}

        return {
            "running": self.running,
            "queue_size": self._q.qsize(),
            "events_written": self._events_written,
            "swarm_modules_ready": self._swarm_modules_ready,
            "research_modules_ready": self._research_modules_ready,
            "events_file": str(self.events_file),
            "substrate": substrate_status,
            "last_error": self._last_error,
        }

    def shutdown(self):
        self._stop_event.set()
        self.running = False
        if self._worker:
            self._worker.join(timeout=2.0)
            self._worker = None
