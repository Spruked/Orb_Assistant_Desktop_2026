"""
ORB Safety Guard
Hard-blocks destructive or out-of-bounds actions before execution.
Kant node is the philosophical backbone of all safety decisions:
  "Act only according to that maxim whereby you can at the same time
   will that it should become a universal law."

Safety levels:
  ALLOW  — execute freely
  WARN   — execute but flag to user
  BLOCK  — refuse execution, return reason
"""

from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple


# ──────────────────────────────────────────────
# Rule definitions
# ──────────────────────────────────────────────

@dataclass
class SafetyRule:
    name:        str
    level:       str   # "warn" | "block"
    description: str

    def matches(self, tool_name: str, args: Dict[str, Any]) -> bool:
        raise NotImplementedError


class CoordinateBoundsRule(SafetyRule):
    """Block clicks/moves that land outside the screen."""

    def __init__(self, max_x: int = 7680, max_y: int = 4320):
        super().__init__(
            name="coordinate_bounds",
            level="block",
            description="Coordinates must be within screen bounds"
        )
        self.max_x = max_x
        self.max_y = max_y

    def matches(self, tool_name: str, args: Dict[str, Any]) -> bool:
        if tool_name not in ("orb_click", "orb_move_mouse", "orb_scroll", "orb_browser_click"):
            return False
        x = args.get("x", 0)
        y = args.get("y", 0)
        return (
            x < 0 or y < 0 or
            x > self.max_x or y > self.max_y
        )


class DestructiveCommandRule(SafetyRule):
    """Block type commands that look like destructive shell operations."""

    DANGEROUS_PATTERNS = [
        "rm -rf", "format c:", "del /f", "mkfs",
        "dd if=/dev/zero", ":(){ :|:& };:", "sudo rm",
        "wipe ", "shred ", "fdisk",
    ]

    def __init__(self):
        super().__init__(
            name="destructive_command",
            level="block",
            description="Typing destructive system commands is not allowed"
        )

    def matches(self, tool_name: str, args: Dict[str, Any]) -> bool:
        if tool_name not in ("orb_type", "orb_browser_type"):
            return False
        text = args.get("text", "").lower()
        return any(pat in text for pat in self.DANGEROUS_PATTERNS)


class ExcessiveWaitRule(SafetyRule):
    """Warn on waits longer than 30 seconds."""

    def __init__(self):
        super().__init__(
            name="excessive_wait",
            level="warn",
            description="Wait exceeds 30 seconds — this may hang the ORB session"
        )

    def matches(self, tool_name: str, args: Dict[str, Any]) -> bool:
        return tool_name == "orb_wait" and args.get("seconds", 0) > 30


class EmptyTypeRule(SafetyRule):
    """Block type calls with empty text."""

    def __init__(self):
        super().__init__(
            name="empty_type",
            level="block",
            description="Cannot type empty text"
        )

    def matches(self, tool_name: str, args: Dict[str, Any]) -> bool:
        return tool_name in ("orb_type", "orb_browser_type") and not args.get("text", "").strip()


class MaliciousURLRule(SafetyRule):
    """Warn on navigation to known malicious patterns."""

    SUSPICIOUS = ["javascript:", "data:text/html", "vbscript:"]

    def __init__(self):
        super().__init__(
            name="suspicious_url",
            level="block",
            description="Suspicious URL pattern detected"
        )

    def matches(self, tool_name: str, args: Dict[str, Any]) -> bool:
        if tool_name not in ("orb_browser_navigate",):
            return False
        url = args.get("url", "").lower()
        return any(p in url for p in self.SUSPICIOUS)


# ──────────────────────────────────────────────
# Safety Guard
# ──────────────────────────────────────────────

class ORBSafetyGuard:
    """
    Evaluates all registered safety rules before any tool execution.
    Returns (allowed: bool, reason: str).
    A BLOCK-level rule match returns (False, reason).
    A WARN-level rule match returns (True, reason) — execution proceeds.
    """

    def __init__(self):
        self._rules: List[SafetyRule] = [
            CoordinateBoundsRule(),
            DestructiveCommandRule(),
            ExcessiveWaitRule(),
            EmptyTypeRule(),
            MaliciousURLRule(),
        ]
        self._block_log: List[Dict[str, Any]] = []

    def evaluate(self, tool_name: str, args: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Returns (allowed, reason).
        allowed=False means execution must not proceed.
        reason is human-readable.
        """
        for rule in self._rules:
            if rule.matches(tool_name, args):
                entry = {
                    "tool":   tool_name,
                    "rule":   rule.name,
                    "level":  rule.level,
                    "reason": rule.description,
                    "args":   args,
                }
                self._block_log.append(entry)

                if rule.level == "block":
                    return False, f"[{rule.name}] {rule.description}"
                else:
                    return True, f"[WARN:{rule.name}] {rule.description}"

        return True, ""

    def add_rule(self, rule: SafetyRule) -> None:
        self._rules.append(rule)

    def block_log(self) -> List[Dict[str, Any]]:
        return list(self._block_log)
