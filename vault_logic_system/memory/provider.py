"""
Single access point to the Vault Logic System's memory subsystem (A.I.M.S.).

Hosts (the Desktop ORB, scripts, tests) never construct AIMSMemorySystem
themselves; they call ``get_memory()``. That is what keeps memory a single
source of truth: one binding file, one store path, one process-wide instance.

The provider is stdlib-only. PyYAML is used for the binding file when it is
installed; otherwise the built-in defaults (identical to aims_binding.yaml)
are used.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import Any, Dict, Optional

FRAMEWORK_ROOT = Path(__file__).resolve().parents[1]
BINDING_FILE = Path(__file__).resolve().parent / "aims_binding.yaml"

_DEFAULT_BINDING: Dict[str, Any] = {
    "authority": "aims",
    "package": "memory/aims",
    "store_path_env": "ORB_AIMS_STORE_PATH",
    "default_store_path": "R:/Substrate_Vault_R/vaults/orb_assistant_desktop/aims",
    "security_mode_env": "AIMS_SECURITY_MODE",
}

_lock = threading.RLock()
_instance = None
_instance_path: Optional[Path] = None


def load_binding() -> Dict[str, Any]:
    """Return the ``memory:`` section of aims_binding.yaml (or the defaults)."""
    binding = dict(_DEFAULT_BINDING)
    try:
        import yaml  # type: ignore

        loaded = yaml.safe_load(BINDING_FILE.read_text(encoding="utf-8")) or {}
        binding.update(loaded.get("memory", {}))
    except Exception:
        pass
    return binding


def aims_root(binding: Optional[Dict[str, Any]] = None) -> Path:
    override = os.getenv("ORB_AIMS_ROOT")
    if override:
        return Path(override)
    return FRAMEWORK_ROOT / (binding or load_binding())["package"]


def store_path(binding: Optional[Dict[str, Any]] = None) -> Path:
    binding = binding or load_binding()
    return Path(os.getenv(binding["store_path_env"]) or binding["default_store_path"]).expanduser()


def _keyring(binding: Dict[str, Any]) -> Dict[str, Any]:
    """Runtime-only key material for authenticated mode (never serialized)."""
    import json

    names = binding.get("keyring_env") or {}
    keys: Dict[str, str] = {}
    keys_file = os.getenv(names.get("keys_file", "AIMS_GLYPH_KEYS_FILE"))
    if keys_file:
        raw = json.loads(Path(keys_file).read_text(encoding="utf-8"))
        keys.update(raw.get("keys", raw) if isinstance(raw, dict) else {})
    key_id = os.getenv(names.get("key_id", "AIMS_GLYPH_KEY_ID"))
    key = os.getenv(names.get("key", "AIMS_GLYPH_KEY"))
    if key:
        if not key_id:
            raise RuntimeError("AIMS_GLYPH_KEY_ID is required when AIMS_GLYPH_KEY is set")
        keys[key_id] = key
    return {"glyph_keys": keys or None, "glyph_key_id": key_id}


def _import_aims(root: Path):
    root_text = str(root)
    if root_text not in sys.path:
        sys.path.insert(0, root_text)
    import memory_core  # noqa: WPS433 (deliberate late import: path set above)

    return memory_core


def get_memory(path: Optional[Path] = None, **overrides: Any):
    """Return the process-wide AIMSMemorySystem, creating it on first use.

    ``path`` overrides the configured store path (tests use a temp dir).
    A second call with a different path returns the existing instance's
    path mismatch as an error: a process has exactly one memory.
    """
    global _instance, _instance_path
    with _lock:
        binding = load_binding()
        target = Path(path) if path is not None else store_path(binding)
        if _instance is not None:
            if _instance_path != target:
                raise RuntimeError(
                    f"Memory already open at {_instance_path}; refusing to open a second store at {target}"
                )
            return _instance
        memory_core = _import_aims(aims_root(binding))
        target.mkdir(parents=True, exist_ok=True)
        mode = os.getenv(binding.get("security_mode_env", "AIMS_SECURITY_MODE")) or None
        kwargs: Dict[str, Any] = {"security_mode": mode, **_keyring(binding), **overrides}
        _instance = memory_core.AIMSMemorySystem(target, **{k: v for k, v in kwargs.items() if v is not None})
        _instance_path = target
        return _instance


def close_memory() -> None:
    global _instance, _instance_path
    with _lock:
        if _instance is not None:
            try:
                _instance.close()
            finally:
                _instance = None
                _instance_path = None
