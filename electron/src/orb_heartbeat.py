"""Heartbeat and lifecycle contract for all ORB shells.

Every ORB must be able to report its own state. If it cannot, it is not
production-ready (ORB Standard XI).

Emitted on the stdout JSON-line channel consumed by orb-bridge.js.
"""

import json
import os
import sys
import time
import threading
from typing import Dict, Optional

ORB_STANDARD_VERSION = "1.0.0"

_HEARTBEAT_INTERVAL_S = float(os.getenv("ORB_HEARTBEAT_INTERVAL_S", "30"))


class OrbHeartbeat:
    """Manages periodic heartbeat emission and lifecycle state."""

    def __init__(self, orb_id: str, orb_shell: str, emit_fn):
        self.orb_id = orb_id
        self.orb_shell = orb_shell
        self._emit = emit_fn
        self._started_at = time.time()
        self._last_heartbeat: Optional[float] = None
        self._last_route: Optional[str] = None
        self._last_error: Optional[str] = None
        self._provider_status: str = "unknown"
        self._router_version: str = "1.0.0"
        self._cognition_mode: str = "deterministic"
        self._active_permissions: list = []
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._running = False

    # ------------------------------------------------------------------
    # Public state setters (called by the orb as it processes)
    # ------------------------------------------------------------------

    def record_route(self, route: str):
        with self._lock:
            self._last_route = route

    def record_error(self, error: str):
        with self._lock:
            self._last_error = error

    def set_provider_status(self, status: str):
        with self._lock:
            self._provider_status = status

    def set_cognition_mode(self, mode: str):
        with self._lock:
            self._cognition_mode = mode

    def set_permissions(self, permissions: list):
        with self._lock:
            self._active_permissions = list(permissions)

    # ------------------------------------------------------------------
    # Snapshot
    # ------------------------------------------------------------------

    def snapshot(self) -> Dict:
        """Return the current lifecycle state as a compliant heartbeat payload."""
        with self._lock:
            return {
                "orb_standard_version": ORB_STANDARD_VERSION,
                "orb_id": self.orb_id,
                "orb_shell": self.orb_shell,
                "heartbeat": "ok",
                "uptime_s": round(time.time() - self._started_at, 1),
                "router_version": self._router_version,
                "provider_status": self._provider_status,
                "cognition_mode": self._cognition_mode,
                "last_route": self._last_route,
                "last_error": self._last_error,
                "active_permissions": self._active_permissions,
                "timestamp": time.time(),
            }

    # ------------------------------------------------------------------
    # Periodic emission
    # ------------------------------------------------------------------

    def start(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="orb-heartbeat")
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            self._beat()
            time.sleep(_HEARTBEAT_INTERVAL_S)

    def _beat(self):
        payload = self.snapshot()
        self._last_heartbeat = payload["timestamp"]
        self._emit({"type": "heartbeat", "data": payload})

    def emit_now(self):
        """Force an immediate heartbeat — call on startup and shutdown."""
        self._beat()
