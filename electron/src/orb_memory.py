"""
orb_memory.py -- the Desktop ORB's single memory interface.

Memory architecture (single source of truth):

    Desktop ORB  ->  OrbMemory (this file)  ->  vault_logic_system/memory/provider.py
                                              ->  A.I.M.S. (vault_logic_system/memory/aims)

Nothing else in the ORB persists memory. The old stores this module replaces:
legacy-observer.js JSONL files, the file-per-hash VaultManager, and the sqlite
behaviour learner.

Tiers:
  short-term   high-frequency / unproven material (cursor habits, presence,
               pending user turns). Volatile, decaying, capped. Never written
               to the ledger.
  long-term    completed interactions and promoted material: append-only,
               hash + Glyph chained, tri-timestamped.
  vault/SKG    judged claims (A Posteriori atoms) derived from long-term entries.

Responsiveness rules (a slow memory must never stall movement or cognition):
  * The cursor/presence hot path only takes ``_stm_lock`` and only touches the
    short-term cache.
  * Ledger writes are slow (A.I.M.S. re-verifies the chain on each write) so
    completed interactions are committed by a background writer thread.
  * Vault/SKG/index work takes ``_vault_lock`` and never holds ``_stm_lock``
    while it runs.
  * Every public method degrades to a bounded in-process fallback and reports
    ``available: False`` instead of raising.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import queue
import sys
import threading
import time
from collections import OrderedDict
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

REPO_ROOT = Path(__file__).resolve().parents[2]
VLS_ROOT = Path(os.getenv("ORB_VLS_ROOT") or (REPO_ROOT / "vault_logic_system"))

_TOPIC_MAP = {
    "family": ["abby", "family", "daughter", "father"],
    "fear": ["fear", "scared", "panic", "afraid"],
    "truth": ["truth", "honest", "lie"],
    "work": ["build", "work", "business", "project"],
    "love": ["love", "care", "heart", "relationship"],
    "legacy": ["legacy", "inherit", "future"],
    "money": ["money", "cash", "debt", "bills"],
    "faith": ["faith", "hope", "pray", "god"],
}


def extract_topics(text: str) -> List[str]:
    lowered = str(text or "").lower()
    found = [topic for topic, words in _TOPIC_MAP.items() if any(word in lowered for word in words)]
    return found or ["general"]


def stable_key(value: Any) -> str:
    text = json.dumps(value, sort_keys=True, default=str) if isinstance(value, (dict, list)) else str(value)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _load_provider():
    existing = sys.modules.get("vls_memory_provider")
    if existing is not None:
        return existing  # one provider module per process keeps the one-store guard intact
    spec = importlib.util.spec_from_file_location("vls_memory_provider", VLS_ROOT / "memory" / "provider.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["vls_memory_provider"] = module
    spec.loader.exec_module(module)
    return module


class OrbMemory:
    PROMOTE_PER_CYCLE = 5
    REINFORCE_PER_CYCLE = 10
    WRITER_QUEUE_MAX = 2000

    def __init__(self, store_path: Optional[Path] = None, memory: Any = None, maintain_interval_s: float = 60.0):
        self._stm_lock = threading.RLock()     # short-term cache + key maps (hot path)
        self._vault_lock = threading.RLock()   # vault, SKG, indexes, promotion, maintenance
        self._count_lock = threading.Lock()
        self.available = False
        self.degraded_reason: Optional[str] = None
        self.store_path: Optional[Path] = None
        self.mem = memory
        self.maintain_interval_s = maintain_interval_s
        self.last_maintenance_at = 0.0
        self.last_maintenance: Dict[str, Any] = {}
        self._stm_keys: Dict[str, str] = {}               # logical key -> STM item id
        self._promoted_stm: "OrderedDict[str, float]" = OrderedDict()   # STM item ids already promoted
        self._reinforced_at: Dict[str, float] = {}                      # STM item id -> last reinforcement time
        self._atoms_by_key: Dict[str, Dict[str, Any]] = {}  # logical key -> {atom_id, entry_id}
        self._fallback: "OrderedDict[str, Any]" = OrderedDict()  # bounded, non-persistent
        self._counters = {"interactions": 0, "observations": 0, "promotions": 0, "errors": 0, "writes_dropped": 0}
        self._queue: "queue.Queue[Callable[[], None]]" = queue.Queue(maxsize=self.WRITER_QUEUE_MAX)
        self._writer: Optional[threading.Thread] = None
        self._writer_stop = threading.Event()
        try:
            if self.mem is None:
                provider = _load_provider()
                self.mem = provider.get_memory(store_path)
                self.store_path = provider.store_path() if store_path is None else Path(store_path)
            else:
                self.store_path = Path(store_path) if store_path else None
            self._index_atoms()
            self.available = True
            self._start_writer()
        except Exception as error:  # memory must never stop the ORB
            self.degraded_reason = f"{type(error).__name__}: {error}"
            self.mem = None

    # ---------- helpers ----------

    def _bump(self, name: str, amount: int = 1) -> None:
        with self._count_lock:
            self._counters[name] += amount

    def _fail(self, error: Exception) -> None:
        self._bump("errors")
        self.degraded_reason = f"{type(error).__name__}: {error}"

    def _index_atoms(self) -> None:
        for atom in self.mem.vault.all_atoms():
            key = (atom.metadata or {}).get("orb_key")
            if key:
                self._atoms_by_key[key] = {"atom_id": atom.atom_id, "entry_id": (atom.derived_from or [None])[0]}

    @staticmethod
    def _entry_types():
        import memory_core  # resolved on sys.path by the provider
        return memory_core.EntryType

    def _fallback_put(self, key: str, value: Any) -> None:
        self._fallback[key] = value
        while len(self._fallback) > 200:
            self._fallback.popitem(last=False)

    # ---------- background writer (ledger commits) ----------

    def _start_writer(self) -> None:
        self._writer = threading.Thread(target=self._writer_loop, name="OrbMemoryWriter", daemon=True)
        self._writer.start()

    def _writer_loop(self) -> None:
        while not self._writer_stop.is_set() or not self._queue.empty():
            try:
                job = self._queue.get(timeout=0.25)
            except queue.Empty:
                continue
            try:
                job()
            except Exception as error:
                self._fail(error)
            finally:
                self._queue.task_done()

    def _enqueue(self, job: Callable[[], None]) -> bool:
        try:
            self._queue.put_nowait(job)
            return True
        except queue.Full:
            self._bump("writes_dropped")
            return False

    def flush(self, timeout: float = 10.0) -> bool:
        """Wait for queued ledger writes (used at shutdown and in tests)."""
        deadline = time.monotonic() + timeout
        while self._queue.unfinished_tasks and time.monotonic() < deadline:
            time.sleep(0.01)
        return not self._queue.unfinished_tasks

    # ---------- short-term ----------

    def observe(self, kind: str, content: Any, tags: Optional[List[str]] = None, key: Optional[str] = None) -> Optional[str]:
        """Short-term only. With ``key`` the same logical item is updated and re-touched."""
        payload = {"kind": kind, "content": content, "key": key}
        self._bump("observations")
        if not self.available:
            with self._stm_lock:
                self._fallback_put(key or f"{kind}:{time.time()}", payload)
            return None
        try:
            with self._stm_lock:
                item_id = self._stm_keys.get(key) if key else None
                item = self.mem.short_term.get(item_id) if item_id else None
                if item is not None:
                    item.content = payload
                    self.mem.short_term.touch(item_id)
                    return item_id
                item = self.mem.observe(payload, tags=[kind, *(tags or [])])
                if key:
                    self._stm_keys[key] = item.item_id
                return item.item_id
        except Exception as error:
            self._fail(error)
            return None

    def recent(self, limit: int = 10, kind: Optional[str] = None) -> List[Dict[str, Any]]:
        with self._stm_lock:
            if not self.available:
                return list(self._fallback.values())[-limit:]
            items = sorted(self.mem.short_term.all_items(), key=lambda i: i.last_touched, reverse=True)
            rows = [i for i in items if kind is None or (i.content or {}).get("kind") == kind]
            return [{"item_id": i.item_id, "vivacity": round(i.vivacity, 3), **(i.content or {})} for i in rows[:limit]]

    # ---------- long-term ----------

    def interaction(self, user_text: str, orb_text: str = "", channel: str = "desktop_chat",
                    metadata: Optional[Dict[str, Any]] = None, request_id: Optional[str] = None) -> Optional[str]:
        """A user turn. A pending turn (no reply yet) stays short-term; a completed turn is
        committed to the ledger by the background writer (returns None; the commit is queued)."""
        topics = extract_topics(f"{user_text} {orb_text}")
        record = {"user_text": user_text, "orb_text": orb_text, "channel": channel,
                  "topics": topics, "request_id": request_id}
        self._bump("interactions")
        if not orb_text:
            self.observe("interaction_pending", record, tags=["interaction", channel],
                         key=f"pending:{request_id or user_text[:64]}")
            return None
        if not self.available:
            with self._stm_lock:
                self._fallback_put(f"interaction:{time.time()}", record)
            return None

        def commit() -> None:
            entry = self.mem.commit(self._entry_types().INTERACTION, record,
                                    metadata={"channel": channel, **(metadata or {})}, writer_id="orb")
            self.observe("interaction", {"entry_id": entry.entry_id, **record}, tags=["interaction", channel])

        self._enqueue(commit)
        return None

    def remember(self, statement: str, content: Any, key: Optional[str] = None,
                 metadata: Optional[Dict[str, Any]] = None, confidence: float = 0.5) -> Optional[str]:
        """Commit to long-term and distil an A Posteriori vault atom (synchronous, off the hot path)."""
        if not self.available:
            with self._stm_lock:
                self._fallback_put(key or statement, content)
            return None
        try:
            with self._vault_lock:
                entry = self.mem.commit(self._entry_types().LEARNING, {"statement": statement, "data": content},
                                        metadata=metadata, writer_id="orb")
                atom_meta = {**(metadata or {}), "orb_key": key} if key else metadata
                atom = self.mem.derive_aposteriori(statement, [entry], metadata=atom_meta, initial_confidence=confidence)
                if key:
                    self._atoms_by_key[key] = {"atom_id": atom.atom_id, "entry_id": entry.entry_id}
            self._bump("promotions")
            return atom.atom_id
        except Exception as error:
            self._fail(error)
            return None

    def recall(self, query: str, limit: int = 5) -> Dict[str, Any]:
        """Episodes (long-term ledger matches) and judged knowledge (vault retrieval)."""
        if not self.available:
            return {"available": False, "episodes": [], "knowledge": []}
        try:
            with self._vault_lock:
                episodes = [e.to_dict() for e in self.mem.long_term.search_entries(
                    entry_type=self._entry_types().INTERACTION, content_keyword=query)][-limit:]
                knowledge = self.mem.retrieve(query, "COLLECTIVE", limit)
            return {"available": True, "episodes": episodes, "knowledge": knowledge.get("results", knowledge)}
        except Exception as error:
            self._fail(error)
            return {"available": False, "episodes": [], "knowledge": [], "error": str(error)}

    # ---------- vault-manager semantics (used by the controller and HabitTracker) ----------

    def vault_lookup(self, key: str) -> Optional[Dict[str, Any]]:
        if not self.available:
            with self._stm_lock:
                value = self._fallback.get(f"vault:{key}")
            return {"source": "FALLBACK", "data": value["content"]["data"]} if value else None
        try:
            with self._stm_lock:
                item_id = self._stm_keys.get(f"vault:{key}")
                item = self.mem.short_term.get(item_id) if item_id else None
                if item is not None and item.vivacity >= 0.05:
                    return {"source": "SHORT_TERM", "data": item.content["content"]["data"]}
            ref = self._atoms_by_key.get(f"vault:{key}")
            if ref and ref.get("entry_id"):
                entry = self.mem.long_term.read_entry(entry_id=ref["entry_id"])
                if entry is not None:
                    return {"source": "LONG_TERM", "data": entry.content.get("content", {}).get("data")}
            return None
        except Exception as error:
            self._fail(error)
            return None

    def vault_store(self, key: str, data: Any) -> None:
        """Hot path: short-term only. Recurring keys are promoted by ``maintain``."""
        self.observe("vault", {"data": data, "key": key}, tags=["vault"], key=f"vault:{key}")

    # ---------- promotion / maintenance ----------

    def promote_pending(self) -> int:
        """Commit recurring short-term items to long-term memory and reinforce active ones."""
        if not self.available:
            return 0
        with self._stm_lock:
            candidates = list(self.mem.short_term.promotion_candidates())
        promoted = reinforced = 0
        with self._vault_lock:
            for item in candidates:
                body = item.content or {}
                logical = body.get("key") or item.item_id
                if item.item_id in self._promoted_stm:
                    # Sustained recurrence reinforces the vault atom (only if touched since last time).
                    ref = self._atoms_by_key.get(logical)
                    if (ref and reinforced < self.REINFORCE_PER_CYCLE
                            and item.last_touched > self._reinforced_at.get(item.item_id, 0.0)):
                        try:
                            if self.mem.vault.reinforce(ref["atom_id"], 0.1) is not None:
                                self._reinforced_at[item.item_id] = time.time()
                                reinforced += 1
                        except Exception as error:
                            self._fail(error)
                    continue
                if promoted >= self.PROMOTE_PER_CYCLE:
                    continue
                try:
                    statement = f"{body.get('kind', 'observation')}: {logical}"
                    atom = self.mem.promote_from_short_term(item, statement, metadata={"orb_key": logical})
                    self._promoted_stm[item.item_id] = time.time()
                    while len(self._promoted_stm) > 2000:
                        self._promoted_stm.popitem(last=False)
                    self._atoms_by_key[logical] = {"atom_id": atom.atom_id, "entry_id": (atom.derived_from or [None])[0]}
                    promoted += 1
                    self._bump("promotions")
                except Exception as error:
                    self._fail(error)
        return promoted

    def truths(self, prefix: str = "", min_confidence: float = 0.0, limit: int = 50) -> List[Dict[str, Any]]:
        """Active vault atoms whose logical key starts with ``prefix`` (judged, reinforced knowledge)."""
        if not self.available:
            return []
        rows = []
        with self._vault_lock:
            for atom in self.mem.vault.all_atoms():
                key = (atom.metadata or {}).get("orb_key") or ""
                if atom.status.value == "active" and key.startswith(prefix) and atom.confidence >= min_confidence:
                    rows.append({"key": key, "statement": atom.statement, "confidence": atom.confidence,
                                 "support_count": atom.support_count, "atom_id": atom.atom_id})
        rows.sort(key=lambda r: (-r["confidence"], -r["support_count"]))
        return rows[:limit]

    def maintain(self, force: bool = False) -> Optional[Dict[str, Any]]:
        now = time.time()
        if not self.available or (not force and now - self.last_maintenance_at < self.maintain_interval_s):
            return None
        self.last_maintenance_at = now
        try:
            promoted = self.promote_pending()
            with self._stm_lock:
                evicted = self.mem.short_term.sweep()
                self._stm_keys = {k: v for k, v in self._stm_keys.items() if self.mem.short_term.get(v) is not None}
            with self._vault_lock:
                self.mem.skg.recursive_self_evaluate(max_passes=1)
                self.mem.indexes.rebuild(self.mem.vault)
            self.last_maintenance = {"at": now, "promoted": promoted, "stm_evicted": evicted}
            return self.last_maintenance
        except Exception as error:
            self._fail(error)
            return None

    # ---------- status / shutdown ----------

    def status(self, deep: bool = False) -> Dict[str, Any]:
        with self._count_lock:
            counters = dict(self._counters)
        base = {
            "authority": "aims",
            "available": self.available,
            "degraded_reason": self.degraded_reason,
            "store_path": str(self.store_path) if self.store_path else None,
            "counters": counters,
            "write_queue": self._queue.qsize(),
            "last_maintenance": self.last_maintenance,
        }
        if not self.available:
            return {**base, "fallback_items": len(self._fallback)}
        try:
            ltm = self.mem.long_term
            with self._stm_lock:
                base["short_term"] = self.mem.short_term.stats()
            base["long_term"] = {"total_entries": ltm.total_entries, "last_sequence": ltm.last_sequence,
                                 "security_mode": ltm.security_mode, "ready_for_writes": ltm.ready}
            if deep:
                with self._vault_lock:
                    base["long_term"] = ltm.get_statistics()
                    base["vault"] = self.mem.vault.stats()
        except Exception as error:
            self._fail(error)
        return base

    def close(self) -> None:
        if self.available:
            self.flush()
            try:
                self.maintain(force=True)
            except Exception:
                pass
        self._writer_stop.set()
        if self._writer is not None and self._writer.is_alive():
            self._writer.join(timeout=2.0)
        if self.available:
            try:
                sys.modules["vls_memory_provider"].close_memory()
            except Exception:
                pass
        self.available = False


_singleton: Optional[OrbMemory] = None
_singleton_lock = threading.Lock()


def get_orb_memory() -> OrbMemory:
    """Process-wide instance; created on first use, never raises."""
    global _singleton
    with _singleton_lock:
        if _singleton is None:
            _singleton = OrbMemory()
        return _singleton


def reset_orb_memory_for_tests() -> None:
    global _singleton
    with _singleton_lock:
        if _singleton is not None:
            _singleton.close()
        _singleton = None
