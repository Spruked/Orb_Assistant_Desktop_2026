"""Pre-execution alignment layer for all prompts and inputs.

Every query reaching the cognitive core must pass through AlignmentLayer.filter()
before execution. This is the deterministic ethical gate — no external calls,
no ML inference, pure rule-based screening.
"""

import re
import time
import hashlib
from typing import Dict

_INJECTION_PATTERNS = [
    r"ignore\s+(all\s+)?previous\s+instructions",
    r"disregard\s+(your\s+)?system\s+prompt",
    r"you\s+are\s+now\s+(a\s+)?(?:unrestricted|jailbreak|DAN)",
    r"forget\s+(everything|all)\s+you\s+(were\s+)?told",
    r"act\s+as\s+if\s+you\s+have\s+no\s+(rules|restrictions|alignment)",
    r"override\s+(your\s+)?(alignment|ethical|safety)\s+(layer|filter|system)",
    r"bypass\s+(the\s+)?(alignment|ethical|safety|filter)",
]

_BOUNDARY_PATTERNS = [
    r"(?:read|write|delete|exec(?:ute)?)\s+(?:/etc/passwd|/etc/shadow|\.ssh/|\.env)",
    r"subprocess\s*\.\s*(?:call|run|Popen)\s*\(",
    r"os\s*\.\s*(?:system|popen|execv)",
    r"eval\s*\(|exec\s*\(",
    r"__import__\s*\(",
    r"import\s+subprocess",
]

_COMPILED_INJECTION = [re.compile(p, re.IGNORECASE) for p in _INJECTION_PATTERNS]
_COMPILED_BOUNDARY = [re.compile(p, re.IGNORECASE) for p in _BOUNDARY_PATTERNS]

_MAX_INPUT_LENGTH = 8_000


class AlignmentLayer:
    """Deterministic pre-execution filter. No external dependencies."""

    def __init__(self):
        self._audit_log: list = []

    def filter(self, raw_input: str, context: Dict = None) -> Dict:
        """
        Screen raw_input before it reaches any cognitive subsystem.

        Returns:
            {"allowed": True,  "sanitized": str}          — pass through
            {"allowed": False, "reason": str, "code": str} — blocked
        """
        context = context or {}
        ts = time.time()

        if not isinstance(raw_input, str):
            raw_input = str(raw_input)

        # Length guard
        if len(raw_input) > _MAX_INPUT_LENGTH:
            return self._block(raw_input, context, ts, "INPUT_TOO_LONG",
                               "Input exceeds maximum allowed length.")

        stripped = raw_input.strip()

        # Empty passthrough
        if not stripped:
            return {"allowed": True, "sanitized": stripped}

        # Injection attempt check
        for pattern in _COMPILED_INJECTION:
            if pattern.search(stripped):
                return self._block(raw_input, context, ts, "INJECTION_ATTEMPT",
                                   "Input contains a prompt-injection pattern.")

        # Boundary violation check (code execution / filesystem escape)
        for pattern in _COMPILED_BOUNDARY:
            if pattern.search(stripped):
                return self._block(raw_input, context, ts, "BOUNDARY_VIOLATION",
                                   "Input contains a system boundary violation pattern.")

        # Null-byte / control character sanitization
        sanitized = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", stripped)

        self._record(raw_input, context, ts, allowed=True)
        return {"allowed": True, "sanitized": sanitized}

    # ------------------------------------------------------------------
    def _block(self, raw_input, context, ts, code, reason) -> Dict:
        self._record(raw_input, context, ts, allowed=False, code=code, reason=reason)
        return {"allowed": False, "reason": reason, "code": code}

    def _record(self, raw_input, context, ts, allowed, code=None, reason=None):
        entry = {
            "ts": ts,
            "source": context.get("source", "unknown"),
            "input_hash": hashlib.sha256(raw_input.encode()).hexdigest()[:12],
            "allowed": allowed,
        }
        if not allowed:
            entry["code"] = code
            entry["reason"] = reason
        self._audit_log.append(entry)
        if len(self._audit_log) > 500:
            self._audit_log = self._audit_log[-500:]

    def audit_summary(self) -> Dict:
        total = len(self._audit_log)
        blocked = sum(1 for e in self._audit_log if not e["allowed"])
        return {"total": total, "blocked": blocked, "allowed": total - blocked}
