"""
ORB MCP Bridge
Manages the session state between the stdio MCP server and all execution modules.
Tracks request history, tool call metrics, and provides the MCPResult carrier type.
"""

from __future__ import annotations
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


# ──────────────────────────────────────────────
# MCPResult
# ──────────────────────────────────────────────

@dataclass
class MCPResult:
    """Uniform result returned from any MCP tool call."""
    success:   bool
    content:   List[Dict[str, Any]] = field(default_factory=list)
    error:     str  = ""
    tool_name: str  = ""
    request_id: str = field(default_factory=lambda: str(uuid.uuid4())[:8])
    elapsed_ms: float = 0.0

    @classmethod
    def ok(cls, text: str, tool: str = "") -> "MCPResult":
        return cls(success=True, content=[{"type": "text", "text": text}], tool_name=tool)

    @classmethod
    def fail(cls, message: str, tool: str = "") -> "MCPResult":
        return cls(
            success=False,
            content=[{"type": "text", "text": message}],
            error=message,
            tool_name=tool,
        )

    def to_mcp_dict(self) -> Dict[str, Any]:
        return {
            "content": self.content,
            "isError": not self.success,
        }


# ──────────────────────────────────────────────
# Session State
# ──────────────────────────────────────────────

class ORBSession:
    """Tracks request/response history for a single ORB server instance."""

    def __init__(self):
        self._start_time    = time.time()
        self._requests: List[Dict[str, Any]] = []
        self._tool_counts:  Dict[str, int]   = {}
        self._error_counts: Dict[str, int]   = {}

    def record(self, tool: str, success: bool, elapsed_ms: float) -> None:
        self._requests.append({
            "tool":       tool,
            "success":    success,
            "elapsed_ms": elapsed_ms,
            "timestamp":  time.time(),
        })
        self._tool_counts[tool]  = self._tool_counts.get(tool, 0) + 1
        if not success:
            self._error_counts[tool] = self._error_counts.get(tool, 0) + 1

    def summary(self) -> Dict[str, Any]:
        total   = len(self._requests)
        success = sum(1 for r in self._requests if r["success"])
        return {
            "uptime_s":     round(time.time() - self._start_time, 1),
            "total_calls":  total,
            "success_rate": round(success / max(total, 1), 4),
            "tool_counts":  self._tool_counts,
            "error_counts": self._error_counts,
        }

    def recent(self, n: int = 10) -> List[Dict[str, Any]]:
        return self._requests[-n:]


# ──────────────────────────────────────────────
# MCP Bridge
# ──────────────────────────────────────────────

class ORBMCPBridge:
    """
    Singleton bridge between the stdio MCP server and all ORB subsystems.
    Manages session lifecycle, request timing, and capability reporting.
    """

    _instance: Optional["ORBMCPBridge"] = None

    def __init__(self):
        self.session = ORBSession()
        self._active = False

    def start(self) -> None:
        self._active = True

    def stop(self) -> None:
        self._active = False

    @property
    def active(self) -> bool:
        return self._active

    def wrap_call(self, tool: str, result_dict: Dict[str, Any], elapsed_ms: float) -> Dict[str, Any]:
        """Record the call and pass through the MCP result dict."""
        success = not result_dict.get("isError", False)
        self.session.record(tool, success, elapsed_ms)
        return result_dict

    def capabilities(self) -> Dict[str, Any]:
        return {
            "desktop_control":  True,
            "browser_control":  True,
            "clipboard":        True,
            "screenshot":       True,
            "tpc_reasoning":    True,
            "r_substrate":      True,
            "morb_evaluation":  True,
            "safety_guard":     True,
            "llm_optional":     True,
        }


# ── Singleton accessor ────────────────────────────────────────────────────────

_bridge_singleton: Optional[ORBMCPBridge] = None

def get_mcp_bridge() -> ORBMCPBridge:
    global _bridge_singleton
    if _bridge_singleton is None:
        _bridge_singleton = ORBMCPBridge()
    return _bridge_singleton
