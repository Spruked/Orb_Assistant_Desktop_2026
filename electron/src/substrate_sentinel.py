"""R:\ Substrate Sentinel (ORB Standard XII) — Hybrid Protection Layer.

Architecture:
    Core does NOT depend on Sentinel for every breath.
    Core obeys Sentinel for dangerous actions.
    Sentinel watches, logs, hashes, snapshots, and protects.

Three-layer model:
    1. Core Standard  = law / contract       (R:\orb_core_standard\)
    2. Shell Adapter  = permissions / env    (orb-instance.*.ps1)
    3. Sentinel       = guardrail, audit,    (this module)
                        snapshot, quarantine,
                        enforcement on risky ops

Behavior by operation:
    read          — always allowed; no gate; logged only for sensitive paths
    write         — checked against policy; snapshot required if protected
    delete        — forbidden on protected paths; quarantine instead
    rename/move   — treated as write+delete pair; snapshot required
    restructure   — treated as write; snapshot required

Public API (call before any risky filesystem operation):
    sentinel.sentinel_can_read(path, purpose)
    sentinel.sentinel_can_write(path, purpose)
    sentinel.sentinel_require_snapshot(path, operation)
    sentinel.quarantine(path, reason)
    sentinel.before_hash(path) / after_hash(path)
    sentinel.log_change(path, operation, before_hash, after_hash)
"""

import hashlib
import json
import os
import shutil
import sys
import time
from pathlib import Path
from typing import Dict, Optional

_HERE = Path(__file__).parent

# Drive root is two levels above ORB_SYSTEM_ROOT:
#   ORB_SYSTEM_ROOT = /mnt/r/Orb_Assistant_Desktop/system
#   drive root       = /mnt/r
_SYSTEM_ROOT = Path(
    os.getenv("ORB_SYSTEM_ROOT") or (_HERE.parent / "system")
).expanduser()

_SENTINEL_ROOT = Path(
    os.getenv("ORB_SENTINEL_ROOT") or (_SYSTEM_ROOT.parent.parent / "Sentinel")
)
_AUDIT_LOG = _SENTINEL_ROOT / "audit_logs" / "sentinel_events.jsonl"
_SNAPSHOT_DIR = _SENTINEL_ROOT / "snapshots"
_QUARANTINE_DIR = _SENTINEL_ROOT / "quarantine"

_PROTECTED_PATHS_FILE = _SYSTEM_ROOT / "protected_paths.json"

_RISKY_OPS = {"write", "delete", "rename", "move", "merge", "restructure", "bulk_rewrite"}

# Sensitive prefixes that trigger passive logging even on reads
_SENSITIVE_PREFIXES = (
    "vault_system",
    "CALI_System",
    "orb_mesh",
    "vector_indexes",
    "indexes",
    "goat_substrate",
    "CALI_SUBSTRATE",
)


def _load_protected(path: Path) -> list:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("protected", [])
    except Exception as exc:
        print(f"⚠️ SubstrateSentinel: could not load {path}: {exc}", file=sys.stderr)
        return []


class SubstrateSentinel:
    """
    Hybrid sentinel: passive watcher for reads, active gate for writes/deletes.

    Reads:   Core reads directly. Sentinel never blocks a read.
             Call sentinel_can_read() only when you want audit logging.
    Writes:  Core MUST call sentinel_can_write() before touching a protected path.
    Deletes: Core MUST NOT delete protected paths. Use quarantine() instead.
    """

    _instance: Optional["SubstrateSentinel"] = None

    def __init__(self):
        self._protected = _load_protected(_PROTECTED_PATHS_FILE)
        # _SYSTEM_ROOT is the `system` directory inside Orb_Assistant_Desktop.
        # One level up is the orb project root (the anchor for protected_paths.json entries).
        self._orb_root = _SYSTEM_ROOT.parent

    @classmethod
    def get(cls) -> "SubstrateSentinel":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def sentinel_can_read(self, path: str, purpose: str = "") -> Dict:
        """
        Observational only — never blocks. Logs reads on sensitive paths.
        Core does not need to call this for normal standard-file reads.
        Call it when reading vault entries, vector indexes, or mesh state.
        """
        relative = self._to_relative(Path(path))
        rel_parts = Path(relative).parts
        is_sensitive = any(p in rel_parts for p in _SENSITIVE_PREFIXES)
        if is_sensitive:
            self._write_event({
                "operation": "read",
                "path": path,
                "purpose": purpose,
                "sensitive": True,
                "allowed": True,
            })
        return {"allowed": True, "sensitive": is_sensitive}

    def sentinel_can_write(self, path: str, purpose: str = "",
                           intent_token: Optional[str] = None) -> Dict:
        """
        Active gate for writes, renames, moves, merges, bulk rewrites.
        Checks protected_paths.json policy. Snapshots protected files first.
        Returns {"allowed": True} or {"allowed": False, "reason": str}.
        """
        target = Path(path)
        relative = self._to_relative(target)
        entry = self._find_protected(relative)

        if entry is None:
            self._write_event({"operation": "write", "path": path, "purpose": purpose,
                               "protected": False, "allowed": True})
            return {"allowed": True}

        policy = entry.get("policy", "")

        if "write-requires-review" in policy and not intent_token:
            result = {"allowed": False,
                      "reason": f"Write to '{relative}' requires review approval. Reason: {entry['reason']}",
                      "policy": policy}
            self._write_event({"operation": "write", "path": path, "purpose": purpose,
                               "protected": True, "allowed": False, "policy": policy})
            return result

        if "write-requires-intent" in policy and not intent_token:
            result = {"allowed": False,
                      "reason": f"Write to '{relative}' requires intent declaration. Reason: {entry['reason']}",
                      "policy": policy}
            self._write_event({"operation": "write", "path": path, "purpose": purpose,
                               "protected": True, "allowed": False, "policy": policy})
            return result

        # Write is allowed — snapshot first
        self.sentinel_require_snapshot(path, "write")
        self._write_event({"operation": "write", "path": path, "purpose": purpose,
                           "protected": True, "allowed": True, "intent_token": bool(intent_token)})
        return {"allowed": True, "snapshot_taken": True}

    def sentinel_require_snapshot(self, path: str, operation: str = "change") -> Optional[str]:
        """
        Snapshot a file or directory before a risky operation.
        Returns the snapshot path, or None if the source doesn't exist.
        """
        src = Path(path)
        if not src.exists():
            return None
        ts = int(time.time() * 1000)
        snapshot_name = f"{ts}_{src.name}"
        dest_dir = _SNAPSHOT_DIR / operation / src.parent.name
        try:
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / snapshot_name
            if src.is_dir():
                shutil.copytree(src, dest, dirs_exist_ok=False)
            else:
                shutil.copy2(src, dest)
            self._write_event({"operation": "snapshot", "path": path,
                               "snapshot": str(dest), "trigger": operation})
            return str(dest)
        except Exception as exc:
            print(f"⚠️ Sentinel snapshot failed for {path}: {exc}", file=sys.stderr)
            return None

    def quarantine(self, path: str, reason: str = "") -> Optional[str]:
        """
        Move a file to the quarantine folder instead of deleting it.
        This is the only approved way to 'delete' a protected or suspicious file.
        Returns the quarantine destination path.
        """
        src = Path(path)
        if not src.exists():
            return None
        ts = int(time.time() * 1000)
        dest = _QUARANTINE_DIR / f"{ts}_{src.name}"
        try:
            _QUARANTINE_DIR.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            self._write_event({"operation": "quarantine", "path": path,
                               "destination": str(dest), "reason": reason})
            return str(dest)
        except Exception as exc:
            print(f"⚠️ Sentinel quarantine failed for {path}: {exc}", file=sys.stderr)
            return None

    def before_hash(self, path: str) -> Optional[str]:
        """SHA-256 of file before an operation. Store and compare with after_hash."""
        return self._sha256(path)

    def after_hash(self, path: str) -> Optional[str]:
        """SHA-256 of file after an operation."""
        return self._sha256(path)

    def log_change(self, path: str, operation: str,
                   hash_before: Optional[str], hash_after: Optional[str],
                   purpose: str = ""):
        """Record a before/after hash pair for a completed operation."""
        self._write_event({
            "operation": operation,
            "path": path,
            "purpose": purpose,
            "hash_before": hash_before,
            "hash_after": hash_after,
            "content_changed": hash_before != hash_after,
        })

    # ------------------------------------------------------------------
    # Legacy compatibility (keep for any existing callers)
    # ------------------------------------------------------------------

    def check(self, target_path: str, operation: str = "write",
              intent_token: Optional[str] = None) -> Dict:
        """Legacy unified check. Prefer sentinel_can_write() for new code."""
        if operation == "read":
            return self.sentinel_can_read(target_path)
        if operation == "delete":
            entry = self._find_protected(self._to_relative(Path(target_path)))
            if entry and "delete-forbidden" in entry.get("policy", ""):
                return {"allowed": False,
                        "reason": f"Delete forbidden on '{target_path}'. Use sentinel.quarantine() instead.",
                        "policy": entry.get("policy")}
        return self.sentinel_can_write(target_path, intent_token=intent_token)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _to_relative(self, path: Path) -> Path:
        try:
            return path.resolve().relative_to(self._orb_root.resolve())
        except ValueError:
            return path

    def _find_protected(self, relative: Path) -> Optional[dict]:
        for entry in self._protected:
            if self._matches(relative, Path(entry["path"])):
                return entry
        return None

    @staticmethod
    def _matches(relative: Path, protected: Path) -> bool:
        rel_parts = relative.parts
        pro_parts = protected.parts
        return len(pro_parts) <= len(rel_parts) and rel_parts[:len(pro_parts)] == pro_parts

    @staticmethod
    def _sha256(path: str) -> Optional[str]:
        try:
            return hashlib.sha256(Path(path).read_bytes()).hexdigest()
        except Exception:
            return None

    def _write_event(self, event: dict):
        entry = {"ts": time.time(), **event}
        try:
            _AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)
            with open(_AUDIT_LOG, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            pass
