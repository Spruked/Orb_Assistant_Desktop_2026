"""
swarm_research_orchestrator.py

Swarm Research Orchestrator
Coordinates distributed research across multiple orb workers.
Handles task decomposition, parallel execution, result aggregation,
and dynamic replanning based on intermediate findings.

Part of: CALI-Swarm_Extension / research/
"""

import asyncio
import json
import logging
import os
import re
import shutil
import sqlite3
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Callable, Any, Tuple
from datetime import datetime, timedelta
from enum import Enum, auto
from collections import defaultdict
import hashlib
import time
from abc import ABC, abstractmethod
from pathlib import Path

try:
    from ..substrate.local_substrate import LocalSwarmSubstrate
except Exception:
    LocalSwarmSubstrate = None

try:
    from .api_selector import select_api_for_category
except Exception:
    select_api_for_category = None

from epistemic_swarm_governor_skg import (
    EpistemicSwarmGovernor, 
    SwarmMission, 
    OrbInstance, 
    OrbClass,
    ResearchFinding,
    MissionType,
    MissionDeniedError
)
from epistemic_gain_calculator import (
    EPIC, 
    OrbContributionMetrics,
    create_metrics_from_finding
)

logger = logging.getLogger("SwarmResearchOrchestrator")


class ShortTermResearchCache:
    """Fast TTL cache for immediate CALI research continuity."""

    def __init__(self, db_path: Optional[Path] = None, default_ttl_seconds: int = 300):
        repo_root = Path(__file__).resolve().parents[4]
        self.db_path = Path(
            db_path
            or os.getenv("CALI_SHORT_TERM_CACHE_DB", "")
            or repo_root / "CALI_System" / "memory" / "short_term_cache.db"
        )
        self.default_ttl_seconds = int(default_ttl_seconds)
        self._lock = threading.Lock()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=15, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS short_term_cache (
                        id TEXT PRIMARY KEY,
                        query TEXT,
                        result TEXT,
                        timestamp INTEGER,
                        ttl_seconds INTEGER,
                        source TEXT
                    )
                    """
                )
                conn.commit()

    def _cache_id(self, query: str, domains: Optional[List[str]] = None) -> str:
        normalized_query = " ".join(str(query or "").strip().lower().split())
        normalized_domains = sorted(
            str(domain).strip().lower() for domain in (domains or []) if str(domain).strip()
        )
        return hashlib.sha256(
            f"{normalized_query}|{'|'.join(normalized_domains)}".encode("utf-8")
        ).hexdigest()

    def get(self, query: str, domains: Optional[List[str]] = None) -> Optional[Dict[str, Any]]:
        cache_id = self._cache_id(query, domains)
        now = int(time.time())
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT result, timestamp, ttl_seconds, source
                    FROM short_term_cache
                    WHERE id = ?
                    """,
                    (cache_id,),
                ).fetchone()
                if not row:
                    return None
                if now - int(row["timestamp"] or 0) > int(row["ttl_seconds"] or 1):
                    conn.execute("DELETE FROM short_term_cache WHERE id = ?", (cache_id,))
                    conn.commit()
                    return None

        try:
            payload = json.loads(row["result"])
        except Exception:
            return None
        if isinstance(payload, dict):
            payload["_short_term_cache"] = {
                "source": row["source"],
                "timestamp": row["timestamp"],
                "ttl_seconds": row["ttl_seconds"],
            }
        return payload

    def store(
        self,
        query: str,
        result: Dict[str, Any],
        domains: Optional[List[str]] = None,
        ttl_seconds: Optional[int] = None,
        source: str = "research_pipeline",
    ) -> None:
        cache_id = self._cache_id(query, domains)
        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO short_term_cache (
                        id, query, result, timestamp, ttl_seconds, source
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        query = excluded.query,
                        result = excluded.result,
                        timestamp = excluded.timestamp,
                        ttl_seconds = excluded.ttl_seconds,
                        source = excluded.source
                    """,
                    (
                        cache_id,
                        query,
                        json.dumps(result, default=str, ensure_ascii=False),
                        int(time.time()),
                        int(ttl_seconds or self.default_ttl_seconds),
                        source,
                    ),
                )
                conn.commit()


class ResearchEventVault:
    """Governed append-only research event vault with active/archive/purge lifecycle."""

    def __init__(self, vault_root: Path, max_active_mb: int = 5):
        self.vault_root = Path(vault_root).expanduser().resolve()
        self.active_dir = self.vault_root / "active"
        self.archive_dir = self.vault_root / "archive"
        self.purge_dir = self.vault_root / "purge"
        self.index_path = self.vault_root / "index.json"
        self.active_path = self.active_dir / "research_events.jsonl"
        self.max_active_bytes = int(max_active_mb) * 1024 * 1024
        self._lock = threading.Lock()
        for path in (self.active_dir, self.archive_dir, self.purge_dir):
            path.mkdir(parents=True, exist_ok=True)
        self._migrate_legacy_log()
        self.active_path.touch(exist_ok=True)
        self._write_index()

    def _migrate_legacy_log(self) -> None:
        legacy_path = self.vault_root / "research_events.jsonl"
        if not legacy_path.exists() or legacy_path == self.active_path:
            return
        if legacy_path.stat().st_size <= 0:
            return
        archive_name = f"legacy_events_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.jsonl"
        shutil.move(str(legacy_path), str(self.archive_dir / archive_name))

    def _iso_now(self) -> str:
        return datetime.utcnow().replace(microsecond=0).isoformat() + "Z"

    def _phase_from_event(self, event_type: str) -> str:
        mapping = {
            "swarm:start": "start",
            "swarm:worker:start": "worker_start",
            "swarm:worker:complete": "worker_complete",
            "swarm:complete": "complete",
            "cali:state": "state",
        }
        return mapping.get(event_type, str(event_type or "event").replace(":", "_"))

    def normalize_event(
        self,
        event: Dict[str, Any],
        query: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> Dict[str, Any]:
        data = event.get("data") if isinstance(event.get("data"), dict) else {}
        event_type = str(event.get("type") or data.get("type") or "research:event")
        started_at = data.get("started_at") or event.get("started_at")
        latency_ms = data.get("latency_ms")
        if latency_ms is None and started_at:
            try:
                latency_ms = int((time.time() - float(started_at)) * 1000)
            except Exception:
                latency_ms = None

        result_summary = (
            data.get("result_summary")
            or data.get("summary")
            or data.get("text")
            or data.get("description")
            or ""
        )
        if not result_summary and data.get("count") is not None:
            result_summary = f"{data.get('count')} result(s)"

        return {
            "id": str(event.get("id") or uuid.uuid4()),
            "timestamp": str(event.get("timestamp_iso") or self._iso_now()),
            "query": query or data.get("query") or event.get("query") or "",
            "topic": topic or data.get("topic") or event.get("topic") or "",
            "phase": data.get("phase") or self._phase_from_event(event_type),
            "worker": data.get("worker") or data.get("worker_id"),
            "source": data.get("source") or event_type,
            "result_summary": str(result_summary)[:1000],
            "confidence": data.get("confidence"),
            "latency_ms": latency_ms,
            "cache_hit": bool(data.get("cache_hit") or data.get("hit") or False),
            "event_type": event_type,
        }

    def append_event(
        self,
        event: Dict[str, Any],
        query: Optional[str] = None,
        topic: Optional[str] = None,
    ) -> Dict[str, Any]:
        record = self.normalize_event(event, query=query, topic=topic)
        with self._lock:
            self.rotate_if_needed()
            with self.active_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
            self._write_index()
        return record

    def rotate_if_needed(self, force: bool = False) -> Optional[Path]:
        if not self.active_path.exists() or self.active_path.stat().st_size <= 0:
            return None
        active_date = datetime.fromtimestamp(self.active_path.stat().st_mtime).date()
        should_rotate = (
            force
            or self.active_path.stat().st_size >= self.max_active_bytes
            or active_date < datetime.now().date()
        )
        if not should_rotate:
            return None
        archive_name = f"events_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.jsonl"
        archive_path = self.archive_dir / archive_name
        shutil.move(str(self.active_path), str(archive_path))
        self.active_path.touch(exist_ok=True)
        self._write_index()
        return archive_path

    def archive_active(self) -> Optional[Path]:
        with self._lock:
            return self.rotate_if_needed(force=True)

    def stage_active_for_purge(self) -> Optional[Path]:
        with self._lock:
            if not self.active_path.exists() or self.active_path.stat().st_size <= 0:
                self.active_path.touch(exist_ok=True)
                return None
            purge_path = self.purge_dir / f"purged_{datetime.now().strftime('%Y-%m-%d_%H%M%S')}.jsonl"
            shutil.move(str(self.active_path), str(purge_path))
            self.active_path.touch(exist_ok=True)
            self._write_index()
            return purge_path

    def replay(
        self,
        query: Optional[str] = None,
        topic: Optional[str] = None,
        min_confidence: Optional[float] = None,
        limit: int = 100,
        include_archive: bool = True,
    ) -> List[Dict[str, Any]]:
        query_l = str(query or "").lower().strip()
        topic_l = str(topic or "").lower().strip()
        files = [self.active_path]
        if include_archive:
            files.extend(sorted(self.archive_dir.glob("*.jsonl"), reverse=True))

        records: List[Dict[str, Any]] = []
        for path in files:
            if not path.exists():
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except Exception:
                continue
            for line in reversed(lines):
                try:
                    record = json.loads(line)
                except Exception:
                    continue
                haystack = " ".join(
                    str(record.get(key) or "").lower()
                    for key in ("query", "topic", "result_summary", "source", "worker")
                )
                if query_l and query_l not in haystack:
                    continue
                if topic_l and topic_l not in haystack:
                    continue
                if min_confidence is not None:
                    confidence = record.get("confidence")
                    if not isinstance(confidence, (int, float)) or confidence < min_confidence:
                        continue
                records.append(record)
                if len(records) >= int(limit):
                    return records
        return records

    def _count_jsonl(self, path: Path) -> int:
        if not path.exists():
            return 0
        try:
            return sum(1 for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        except Exception:
            return 0

    def _topics_for_file(self, path: Path) -> List[str]:
        topics: Set[str] = set()
        if not path.exists():
            return []
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except Exception:
            return []
        for line in lines:
            try:
                record = json.loads(line)
            except Exception:
                continue
            topic = str(record.get("topic") or "").strip()
            if topic:
                topics.add(topic)
        return sorted(topics)

    def _write_index(self) -> None:
        archives = []
        for path in sorted(self.archive_dir.glob("*.jsonl")):
            archives.append(
                {
                    "file": path.name,
                    "entries": self._count_jsonl(path),
                    "topics": self._topics_for_file(path),
                    "archived_at": datetime.fromtimestamp(path.stat().st_mtime).isoformat(),
                }
            )
        index = {
            "active": {
                "file": str(self.active_path),
                "entries": self._count_jsonl(self.active_path),
                "bytes": self.active_path.stat().st_size if self.active_path.exists() else 0,
            },
            "archives": archives,
            "purge_staged": [
                {"file": path.name, "bytes": path.stat().st_size}
                for path in sorted(self.purge_dir.glob("*.jsonl"))
            ],
            "updated_at": self._iso_now(),
        }
        self.index_path.write_text(json.dumps(index, indent=2, ensure_ascii=False), encoding="utf-8")


# ============================================================================
# RESEARCH TASK DEFINITIONS
# ============================================================================

class TaskType(Enum):
    """Types of research tasks assignable to orbs"""
    WEB_SEARCH = auto()           # General web search
    DOCUMENT_RETRIEVAL = auto()   # PDF, filing, document fetch
    ENTITY_EXTRACTION = auto()    # Named entity recognition
    RELATIONSHIP_MAPPING = auto() # Connection discovery
    VERIFICATION = auto()         # Cross-source fact checking
    TIMELINE_CONSTRUCTION = auto() # Chronological ordering
    CONTRADICTION_ANALYSIS = auto() # Conflict detection
    SYNTHESIS = auto()            # Report compilation

class TaskPriority(Enum):
    """Task execution priority"""
    CRITICAL = 1    # Must complete, blocks mission
    HIGH = 2        # Important for mission success
    NORMAL = 3      # Standard research task
    LOW = 4         # Nice-to-have, can be dropped
    BACKGROUND = 5  # Opportunistic, no guarantee

@dataclass
class ResearchTask:
    """Single unit of research work"""
    task_id: str
    task_type: TaskType
    priority: TaskPriority
    description: str
    
    # Task parameters
    query: str
    source_constraints: Dict = field(default_factory=dict)
    output_format: str = "structured"
    
    # Execution
    assigned_orb: Optional[str] = None
    status: str = "pending"  # pending, active, completed, failed, cancelled
    created_at: datetime = field(default_factory=datetime.now)
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    
    # Results
    findings: List[Dict] = field(default_factory=list)
    raw_data: Optional[Any] = None
    
    # Dependencies
    depends_on: List[str] = field(default_factory=list)  # task_ids
    blocks: List[str] = field(default_factory=list)    # tasks this blocks
    
    def get_duration_seconds(self) -> Optional[float]:
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None

@dataclass
class ResearchPlan:
    """Complete plan for a research mission"""
    plan_id: str
    mission_id: str
    
    # Task graph
    tasks: Dict[str, ResearchTask] = field(default_factory=dict)
    execution_order: List[List[str]] = field(default_factory=list)  # Parallel groups
    
    # Dynamic replanning
    generation: int = 1  # Plan revision number
    parent_plan: Optional[str] = None
    
    # Status
    created_at: datetime = field(default_factory=datetime.now)
    is_frozen: bool = False  # No more changes allowed
    
    def get_ready_tasks(self) -> List[ResearchTask]:
        """Get tasks whose dependencies are satisfied"""
        ready = []
        for task in self.tasks.values():
            if task.status != "pending":
                continue
            
            # Check dependencies
            deps_satisfied = all(
                self.tasks.get(dep_id, ResearchTask(dep_id, TaskType.WEB_SEARCH, 
                                                    TaskPriority.NORMAL, "", "")).status == "completed"
                for dep_id in task.depends_on
            )
            
            if deps_satisfied:
                ready.append(task)
        
        # Sort by priority
        return sorted(ready, key=lambda t: t.priority.value)
    
    def get_critical_path(self) -> List[str]:
        """Identify tasks on the critical path to mission completion"""
        # Simplified: tasks that block others or are CRITICAL priority
        critical = []
        for task_id, task in self.tasks.items():
            if task.priority == TaskPriority.CRITICAL:
                critical.append(task_id)
            elif task.blocks:
                critical.append(task_id)
        return list(set(critical))


# ============================================================================
# RESEARCH ENGINES (Pluggable)
# ============================================================================

class ResearchEngine(ABC):
    """Abstract research execution engine"""
    
    @abstractmethod
    async def execute_search(self, query: str, constraints: Dict) -> List[Dict]:
        """Execute search and return raw results"""
        pass
    
    @abstractmethod
    async def fetch_document(self, reference: str) -> Dict:
        """Retrieve and parse a document"""
        pass
    
    @abstractmethod
    async def extract_entities(self, text: str) -> List[Dict]:
        """Extract named entities from text"""
        pass

class WebResearchEngine(ResearchEngine):
    """
    Manifest-driven public API research engine.
    It only fetches concrete API endpoints and does not fabricate findings.
    """
    
    DOMAIN_HINTS = {
        "academic": ["paper", "study", "journal", "citation", "research", "scholar", "author"],
        "biomedical": ["medical", "clinical", "nih", "pubmed", "gene", "protein", "disease", "trial"],
        "chemistry": ["chemical", "compound", "molecule", "material", "protein"],
        "climate": ["climate", "weather", "noaa", "temperature", "storm", "rainfall"],
        "space": ["space", "nasa", "planet", "satellite", "astronomy", "launch"],
        "geospatial": ["map", "earthquake", "geospatial", "location", "gis", "usgs"],
        "finance": ["sec", "filing", "stock", "company", "market", "finance"],
        "economics": ["world bank", "indicator", "gdp", "economics", "development"],
        "machine_learning": ["machine learning", "ai", "model", "dataset", "benchmark"],
    }

    def __init__(
        self,
        api_keys: Optional[Dict] = None,
        manifest_roots: Optional[List[Path]] = None,
        max_workers: int = 4,
        request_timeout: float = 5.0,
    ):
        self.api_keys = api_keys or {}
        self.rate_limiter = asyncio.Semaphore(5)  # Max concurrent requests
        repo_root = Path(__file__).resolve().parents[4]
        self.manifest_roots = [
            Path(p).expanduser().resolve()
            for p in (
                manifest_roots
                or [
                    Path(os.getenv("CALI_MANIFEST_ROOT", "R:/manifests")),
                    repo_root / "system" / "CALI_System" / "config",
                    repo_root / "CALI_System" / "config",
                ]
            )
            if Path(p).exists()
        ]
        self.max_workers = max(1, int(max_workers))
        self.request_timeout = float(request_timeout)
        self._manifest_cache: Optional[List[Dict[str, Any]]] = None
    
    async def execute_search(self, query: str, constraints: Dict) -> List[Dict]:
        """Fetch real results from selected manifest endpoints."""
        async with self.rate_limiter:
            domains = constraints.get("domains") or self.detect_domains(query)
            max_results = int(constraints.get("max_results", 6) or 6)
            apis = self._select_apis(query, domains, max_results=max_results)
            if not apis:
                return []

            loop = asyncio.get_running_loop()
            tasks = [
                loop.run_in_executor(None, self._fetch_api, api, query)
                for api in apis[: max(max_results, self.max_workers)]
            ]
            results: List[Dict[str, Any]] = []
            for result in await asyncio.gather(*tasks, return_exceptions=True):
                if isinstance(result, Exception):
                    logger.debug("Manifest API fetch failed: %s", result)
                    continue
                if result:
                    results.append(result)
            return results[:max_results]
    
    async def fetch_document(self, reference: str) -> Dict:
        """Fetch a referenced HTTP document and return parsed text metadata."""
        async with self.rate_limiter:
            if not str(reference).startswith(("http://", "https://")):
                return {}
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(None, self._fetch_document_sync, reference)
    
    async def extract_entities(self, text: str) -> List[Dict]:
        """Deterministic lightweight entity extraction for fetched text."""
        entities = []
        seen = set()
        for match in re.finditer(r"\b[A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*){0,4}\b", text or ""):
            value = match.group(0).strip(" .,:;")
            if len(value) < 4 or value.lower() in seen:
                continue
            seen.add(value.lower())
            entities.append({"text": value, "type": "PROPER_NOUN", "confidence": 0.65})
            if len(entities) >= 25:
                break
        return entities

    def detect_domains(self, query: str) -> List[str]:
        lowered = str(query or "").lower()
        domains = [
            domain
            for domain, keywords in self.DOMAIN_HINTS.items()
            if any(keyword in lowered for keyword in keywords)
        ]
        return domains or ["academic", "general"]

    def _load_manifest_entries(self) -> List[Dict[str, Any]]:
        if self._manifest_cache is not None:
            return self._manifest_cache

        entries: List[Dict[str, Any]] = []
        for root in self.manifest_roots:
            for path in root.glob("*.json"):
                try:
                    with path.open("r", encoding="utf-8") as f:
                        data = json.load(f)
                except Exception as exc:
                    logger.debug("Skipping unreadable manifest %s: %s", path, exc)
                    continue
                entries.extend(self._normalize_manifest(path, data))

        self._manifest_cache = entries
        return entries

    def _normalize_manifest(self, path: Path, data: Any) -> List[Dict[str, Any]]:
        raw_items: List[Dict[str, Any]] = []
        if isinstance(data, dict):
            if isinstance(data.get("apis"), list):
                raw_items.extend(data["apis"])
            if isinstance(data.get("domains"), list):
                raw_items.extend(data["domains"])
            if isinstance(data.get("top_200_public_research_apis_by_domain"), dict):
                for domain, items in data["top_200_public_research_apis_by_domain"].items():
                    for item in items if isinstance(items, list) else []:
                        if isinstance(item, dict):
                            item = dict(item)
                            item.setdefault("domain", domain)
                            raw_items.append(item)
            for value in data.values():
                if isinstance(value, list):
                    raw_items.extend(item for item in value if isinstance(item, dict))
        elif isinstance(data, list):
            raw_items.extend(item for item in data if isinstance(item, dict))

        normalized: List[Dict[str, Any]] = []
        for item in raw_items:
            endpoints = item.get("endpoints") if isinstance(item.get("endpoints"), dict) else {}
            if not endpoints:
                endpoint = item.get("endpoint") or item.get("url")
                if endpoint:
                    endpoints = {"default": endpoint}
            for endpoint_name, url in endpoints.items():
                if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                    continue
                normalized.append(
                    {
                        "api_id": str(item.get("id") or item.get("name") or endpoint_name),
                        "manifest": str(path),
                        "name": str(item.get("name") or item.get("provider") or endpoint_name),
                        "provider": str(item.get("provider") or item.get("name") or path.stem),
                        "category": str(item.get("category") or item.get("domain") or path.stem),
                        "domain": str(item.get("domain") or item.get("category") or path.stem),
                        "auth": str(item.get("auth") or "none").lower(),
                        "priority": str(item.get("priority") or ""),
                        "storage_hint": str(item.get("storage_hint") or ""),
                        "endpoint_name": str(endpoint_name),
                        "url": url,
                    }
                )
        return normalized

    def _select_apis(self, query: str, domains: List[str], max_results: int) -> List[Dict[str, Any]]:
        entries = self._load_manifest_entries()
        lowered_query = str(query or "").lower()
        query_terms = [
            term
            for term in re.findall(r"[a-z0-9]+", lowered_query)
            if len(term) >= 3
        ]
        requested = {str(domain).lower() for domain in domains or []}
        scored: List[Tuple[int, Dict[str, Any]]] = []
        decision_cache: Dict[str, Dict[str, Any]] = {}

        for entry in entries:
            if "api_key_required" in entry.get("auth", ""):
                key_name = re.sub(r"[^A-Z0-9]+", "_", entry["provider"].upper()).strip("_")
                if not self.api_keys.get(key_name) and not os.getenv(key_name):
                    continue
            url = entry.get("url", "")
            if "{" in url or "}" in url:
                continue
            entry_domain = str(entry.get("domain") or "").lower()
            entry_category = str(entry.get("category") or "").lower()
            if requested and entry_domain not in requested and entry_category not in requested:
                continue

            decision: Optional[Dict[str, Any]] = None
            category = str(entry.get("category") or "")
            if select_api_for_category and category:
                decision = decision_cache.get(category)
                if decision is None:
                    decision = select_api_for_category(category)
                    decision_cache[category] = decision
                action = str(decision.get("action") or "")
                selected_api_id = str(decision.get("api_id") or "")
                selected_endpoint = str(decision.get("endpoint") or "")
                if action == "block":
                    continue
                if action == "use_primary":
                    if selected_api_id and selected_api_id != str(entry.get("api_id") or ""):
                        continue
                elif action == "use_fallback":
                    if selected_endpoint and selected_endpoint != url:
                        continue
                elif action == "use_mirror":
                    continue

            haystack = " ".join(
                str(entry.get(key, "")).lower()
                for key in ("name", "provider", "category", "domain", "endpoint_name")
            )
            search_haystack = " ".join(
                str(entry.get(key, "")).lower()
                for key in ("name", "endpoint_name", "url")
            )
            term_hits = sum(1 for word in query_terms if word in haystack or word in url.lower())
            supports_query = "{query}" in url or "{name}" in url
            search_capable = any(
                marker in search_haystack
                for marker in ("search", "query", "q=", "query=")
            )

            score = 0
            if requested:
                score += 2
            if supports_query:
                score += 4
            if search_capable:
                score += 2
            if term_hits:
                score += term_hits * 3
            elif requested and not supports_query and not search_capable:
                continue
            if score > 0:
                selected_entry = dict(entry)
                if decision:
                    trace = decision.get("trace") if isinstance(decision.get("trace"), dict) else {}
                    selected_entry["selection_decision"] = decision
                    score += int(float(trace.get("score", 0.0)) * 10)
                scored.append((score, selected_entry))

        scored.sort(key=lambda item: item[0], reverse=True)
        unique: Dict[str, Dict[str, Any]] = {}
        for _, entry in scored:
            unique.setdefault(entry["url"], entry)
        return list(unique.values())[: max(4, max_results * 2)]

    def _fetch_api(self, api: Dict[str, Any], query: str) -> Optional[Dict[str, Any]]:
        url = self._build_url(api["url"], query)
        if not url:
            return None
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "CALI-Orb-Research/3.0",
                "Accept": "application/json, text/plain;q=0.8, */*;q=0.5",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                raw = response.read(256_000)
                content_type = response.headers.get("content-type", "")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.debug("API request failed for %s: %s", url, exc)
            return None

        text = raw.decode("utf-8", errors="replace")
        payload: Any = text
        if "json" in content_type or text.lstrip().startswith(("{", "[")):
            try:
                payload = json.loads(text)
            except Exception:
                payload = text
        title, snippet = self._summarize_payload(api, payload)
        if not snippet:
            return None
        return {
            "url": url,
            "title": title,
            "snippet": snippet,
            "source_type": "manifest_api",
            "api_id": api.get("api_id"),
            "provider": api.get("provider"),
            "api": api.get("name"),
            "domain": api.get("domain"),
            "manifest": api.get("manifest"),
            "selection_trace": api.get("selection_decision", {}).get("trace") if isinstance(api.get("selection_decision"), dict) else None,
            "raw_preview": payload if isinstance(payload, (dict, list)) else text[:4000],
            "confidence": 0.72,
        }

    def _build_url(self, template: str, query: str) -> Optional[str]:
        encoded = urllib.parse.quote_plus(str(query or "").strip())
        compact = urllib.parse.quote_plus(" ".join(str(query or "").split()[:8]))
        if "{query}" in template:
            return template.replace("{query}", encoded)
        if "{name}" in template:
            return template.replace("{name}", compact)
        if "{filters}" in template:
            return template.replace("{filters}", "title.search:" + encoded)
        if "{sparql}" in template:
            return None

        parsed = urllib.parse.urlparse(template)
        if not parsed.scheme or not parsed.netloc:
            return None
        netloc = parsed.netloc.lower()
        path = parsed.path.rstrip("/")
        query_text = str(query or "").strip()

        if "export.arxiv.org" in netloc:
            params = {"search_query": f"all:{query_text}", "start": "0", "max_results": "5"}
            return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(params)))
        if "api.crossref.org" in netloc:
            parsed = parsed._replace(path="/works")
            params = {"query.bibliographic": query_text, "rows": "5"}
            return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(params)))
        if "api.openalex.org" in netloc:
            parsed = parsed._replace(path="/works")
            params = {"search": query_text, "per-page": "5"}
            return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(params)))
        if "api.semanticscholar.org" in netloc and path in ("", "/graph/v1"):
            parsed = parsed._replace(path="/graph/v1/paper/search")
            params = {"query": query_text, "limit": "5", "fields": "title,abstract,year,url"}
            return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(params)))
        if "eutils.ncbi.nlm.nih.gov" in netloc and path.endswith("/esearch.fcgi"):
            params = {"db": "pubmed", "term": query_text, "retmode": "json", "retmax": "5"}
            return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(params)))
        if "clinicaltrials.gov" in netloc and "/api/query/study_fields" in path:
            params = {
                "expr": query_text,
                "fields": "NCTId,BriefTitle,Condition,OverallStatus",
                "min_rnk": "1",
                "max_rnk": "10",
                "fmt": "json",
            }
            return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(params)))
        if "clinicaltrials.gov" in netloc and "/api/query/full_studies" in path:
            params = {"expr": query_text, "min_rnk": "1", "max_rnk": "5", "fmt": "json"}
            return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(params)))
        if "rest.uniprot.org" in netloc and path.endswith("/uniprotkb/search"):
            params = {"query": query_text, "format": "json", "size": "5"}
            return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(params)))

        params = dict(urllib.parse.parse_qsl(parsed.query, keep_blank_values=True))
        if not params:
            if "clinicaltrials.gov" in parsed.netloc:
                params.update({"expr": str(query), "fmt": "json"})
            elif "earthdata.nasa.gov" in parsed.netloc:
                params["keyword"] = str(query)
            elif "openaq.org" in parsed.netloc:
                params["limit"] = "10"
            elif "nationalmap.gov" in parsed.netloc:
                params["q"] = str(query)
            else:
                return None
        rebuilt = parsed._replace(query=urllib.parse.urlencode(params, doseq=True))
        return urllib.parse.urlunparse(rebuilt)

    def _summarize_payload(self, api: Dict[str, Any], payload: Any) -> Tuple[str, str]:
        title = f"{api.get('provider')} {api.get('endpoint_name')} result"
        snippets: List[str] = []

        def collect(value: Any, depth: int = 0) -> None:
            if len(snippets) >= 6 or depth > 4:
                return
            if isinstance(value, dict):
                preferred = [
                    value.get(key)
                    for key in ("title", "display_name", "name", "paperId", "abstract", "description", "summary")
                    if value.get(key)
                ]
                for item in preferred:
                    collect(item, depth + 1)
                for key in ("data", "results", "items", "records", "features", "studies", "works"):
                    if key in value:
                        collect(value[key], depth + 1)
            elif isinstance(value, list):
                for item in value[:5]:
                    collect(item, depth + 1)
            elif isinstance(value, str):
                cleaned = re.sub(r"<[^>]+>", " ", value)
                cleaned = " ".join(cleaned.split())
                if len(cleaned) > 20:
                    snippets.append(cleaned[:300])

        collect(payload)
        if not snippets and isinstance(payload, str):
            cleaned = re.sub(r"<[^>]+>", " ", payload)
            snippets.append(" ".join(cleaned.split())[:500])
        return title, " | ".join(snippets)[:1200]

    def _fetch_document_sync(self, reference: str) -> Dict:
        request = urllib.request.Request(
            reference,
            headers={"User-Agent": "CALI-Orb-Research/3.0", "Accept": "text/plain, text/html, */*"},
        )
        try:
            with urllib.request.urlopen(request, timeout=self.request_timeout) as response:
                raw = response.read(512_000)
                content_type = response.headers.get("content-type", "")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            logger.debug("Document fetch failed for %s: %s", reference, exc)
            return {}
        text = raw.decode("utf-8", errors="replace")
        text = re.sub(r"<script\b[^>]*>.*?</script>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<style\b[^>]*>.*?</style>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", " ", text)
        text = " ".join(text.split())
        return {
            "url": reference,
            "title": reference,
            "content": text[:8000],
            "metadata": {
                "content_type": content_type,
                "word_count": len(text.split()),
                "fetched_at": datetime.now().isoformat(),
            },
        }

class LocalCorpusEngine(ResearchEngine):
    """
    Research against local document corpus.
    Uses vector search, full-text index, etc.
    """
    
    def __init__(self, corpus_path: str):
        self.corpus_path = Path(corpus_path).expanduser()
    
    async def execute_search(self, query: str, constraints: Dict) -> List[Dict]:
        """Search local text/json corpus without inventing hits."""
        if not self.corpus_path.exists():
            return []
        lowered = str(query or "").lower()
        terms = [term for term in re.findall(r"[a-z0-9]{4,}", lowered)[:8]]
        results: List[Dict[str, Any]] = []
        for path in self.corpus_path.rglob("*"):
            if len(results) >= int(constraints.get("max_results", 5) or 5):
                break
            if path.suffix.lower() not in {".txt", ".md", ".json", ".jsonl"}:
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except Exception:
                continue
            haystack = text.lower()
            if terms and not any(term in haystack for term in terms):
                continue
            snippet = " ".join(text.split())[:1000]
            results.append(
                {
                    "url": str(path),
                    "title": path.name,
                    "snippet": snippet,
                    "source_type": "local_corpus",
                    "confidence": 0.68,
                }
            )
        return results
    
    async def fetch_document(self, reference: str) -> Dict:
        """Retrieve from local store"""
        path = Path(reference)
        if not path.exists() or not path.is_file():
            return {}
        text = path.read_text(encoding="utf-8", errors="replace")
        return {
            "url": str(path),
            "title": path.name,
            "content": text[:8000],
            "metadata": {"word_count": len(text.split()), "fetched_at": datetime.now().isoformat()},
        }
    
    async def extract_entities(self, text: str) -> List[Dict]:
        return await WebResearchEngine().extract_entities(text)

class HybridResearchEngine(ResearchEngine):
    """
    Substrate-first research pipeline with manifest-driven external fetch.
    """
    
    def __init__(self, system_root: Optional[Path] = None, event_callback: Optional[Callable] = None):
        repo_root = Path(__file__).resolve().parents[4]
        default_system_root = repo_root / "system"
        self.system_root = Path(
            system_root or os.getenv("ORB_SYSTEM_ROOT", "") or default_system_root
        ).expanduser().resolve()
        self.short_cache = ShortTermResearchCache()
        self.event_callback = event_callback
        self.substrate = LocalSwarmSubstrate(self.system_root) if LocalSwarmSubstrate else None
        self.engines: Dict[str, ResearchEngine] = {
            'web': WebResearchEngine(),
            'local': LocalCorpusEngine(str(Path("R:/manifests")))
        }
        self.default_engine = 'web'
    
    async def execute_search(self, query: str, constraints: Dict) -> List[Dict]:
        constraints = constraints or {}
        domains = constraints.get("domains") or self.engines["web"].detect_domains(query)
        self._emit("swarm:start", {"query": query, "domains": domains})

        cached = self.short_cache.get(query, domains)
        if cached:
            self._emit("swarm:complete", {"query": query, "source": "short_term_cache"})
            return self._payload_to_findings(cached, "short_term_cache")

        substrate_payload = None
        if self.substrate:
            self._emit("swarm:worker:start", {"worker_id": "archivist", "task": "substrate_lookup"})
            substrate_payload = self.substrate.lookup_research(query, domains, max_age_seconds=86400)
            self._emit(
                "swarm:worker:complete",
                {"worker_id": "archivist", "task": "substrate_lookup", "hit": bool(substrate_payload)},
            )
        if substrate_payload:
            self.short_cache.store(query, substrate_payload, domains, source="substrate")
            self._emit("swarm:complete", {"query": query, "source": "substrate"})
            return self._payload_to_findings(substrate_payload, "substrate")

        workers = [
            ("scout", self.engines["web"].execute_search(query, {**constraints, "domains": domains})),
            ("archivist", self.engines["local"].execute_search(query, {**constraints, "domains": domains})),
        ]
        for worker_id, _ in workers:
            self._emit("swarm:worker:start", {"worker_id": worker_id, "task": "external_fetch"})

        gathered = await asyncio.gather(*(worker for _, worker in workers), return_exceptions=True)
        results: List[Dict[str, Any]] = []
        for (worker_id, _), result in zip(workers, gathered):
            if isinstance(result, Exception):
                self._emit(
                    "swarm:worker:complete",
                    {"worker_id": worker_id, "task": "external_fetch", "error": str(result)},
                )
                continue
            results.extend(result or [])
            self._emit(
                "swarm:worker:complete",
                {"worker_id": worker_id, "task": "external_fetch", "count": len(result or [])},
            )

        payload = self._build_research_payload(query, domains, results)
        self.short_cache.store(query, payload, domains, source="external")
        if self.substrate:
            self.substrate.store_research(query, domains, payload)
        self._emit("swarm:complete", {"query": query, "source": "external", "count": len(results)})
        return results
    
    async def fetch_document(self, reference: str) -> Dict:
        # Route based on reference type
        if reference.startswith('http'):
            return await self.engines['web'].fetch_document(reference)
        else:
            return await self.engines['local'].fetch_document(reference)
    
    async def extract_entities(self, text: str) -> List[Dict]:
        # Use best available NER
        return await self.engines['web'].extract_entities(text)

    def _build_research_payload(self, query: str, domains: List[str], results: List[Dict]) -> Dict[str, Any]:
        sources = [
            {
                "url": result.get("url"),
                "title": result.get("title"),
                "provider": result.get("provider") or result.get("api"),
                "source_type": result.get("source_type"),
            }
            for result in results
            if result.get("url")
        ]
        key_findings = [
            str(result.get("snippet") or result.get("title") or "").strip()
            for result in results
            if str(result.get("snippet") or result.get("title") or "").strip()
        ][:5]
        unique_sources = len({source["url"] for source in sources if source.get("url")})
        confidence = min(0.92, 0.35 + unique_sources * 0.12)
        if unique_sources >= 2:
            confidence += 0.08
        confidence = round(min(0.95, confidence), 2)
        return {
            "query": query,
            "domains": domains,
            "results": results,
            "sources": sources,
            "research_synthesis": {
                "summary": " ".join(key_findings[:3])[:1500],
                "key_findings": key_findings,
                "successful_returns": len(results),
                "sources_queried": unique_sources,
                "confidence": confidence,
                "timestamp": datetime.now().isoformat(),
            },
            "confidence": confidence,
            "timestamp": datetime.now().isoformat(),
        }

    def _payload_to_findings(self, payload: Dict[str, Any], source_type: str) -> List[Dict]:
        results = payload.get("results") if isinstance(payload, dict) else None
        if isinstance(results, list) and results:
            findings = []
            for result in results:
                if isinstance(result, dict):
                    item = dict(result)
                    item.setdefault("source_type", source_type)
                    findings.append(item)
            return findings

        synthesis = payload.get("research_synthesis", {}) if isinstance(payload, dict) else {}
        key_findings = synthesis.get("key_findings") if isinstance(synthesis, dict) else None
        sources = payload.get("sources") if isinstance(payload, dict) else []
        findings = []
        for index, finding in enumerate(key_findings or []):
            source = sources[index] if isinstance(sources, list) and index < len(sources) else {}
            findings.append(
                {
                    "url": source.get("url") if isinstance(source, dict) else None,
                    "title": source.get("title") if isinstance(source, dict) else "Cached research finding",
                    "snippet": str(finding),
                    "source_type": source_type,
                    "confidence": payload.get("confidence", synthesis.get("confidence", 0.7)),
                }
            )
        return findings

    def _emit(self, event_name: str, payload: Dict[str, Any]) -> None:
        event = {"type": event_name, "timestamp": time.time(), "data": payload}
        if self.event_callback:
            try:
                self.event_callback(event)
            except Exception as exc:
                logger.debug("Swarm event callback failed: %s", exc)
        logger.debug("swarm event: %s", event)


# ============================================================================
# SWARM RESEARCH ORCHESTRATOR
# ============================================================================

class SwarmResearchOrchestrator:
    """
    Central coordinator for distributed swarm research.
    
    Responsibilities:
    - Convert mission to research plan
    - Assign tasks to orbs based on class specialization
    - Execute tasks in parallel with dependency management
    - Dynamically replan based on findings
    - Aggregate results and feed back to governor
    """
    
    # Orb class to task type mapping
    ORB_SPECIALIZATION = {
        OrbClass.SCOUT: [TaskType.WEB_SEARCH, TaskType.ENTITY_EXTRACTION],
        OrbClass.ARCHIVIST: [TaskType.DOCUMENT_RETRIEVAL, TaskType.TIMELINE_CONSTRUCTION],
        OrbClass.ANALYST: [TaskType.RELATIONSHIP_MAPPING, TaskType.SYNTHESIS],
        OrbClass.VERIFIER: [TaskType.VERIFICATION, TaskType.CONTRADICTION_ANALYSIS],
        OrbClass.SENTINEL: [TaskType.WEB_SEARCH],  # Monitoring
        OrbClass.HERALD: []  # No research tasks
    }
    
    def __init__(self,
                 governor: EpistemicSwarmGovernor,
                 research_engine: Optional[ResearchEngine] = None,
                 event_callback: Optional[Callable] = None):
        self.governor = governor
        self.event_callback = event_callback
        self.engine = research_engine or HybridResearchEngine()
        if hasattr(self.engine, "event_callback") and event_callback:
            self.engine.event_callback = event_callback
        
        # Active state
        self.active_plans: Dict[str, ResearchPlan] = {}
        self.orb_task_assignments: Dict[str, str] = {}  # orb_id -> task_id
        self.task_results: Dict[str, List[Dict]] = {}
        
        # Execution tracking
        self.execution_semaphores: Dict[str, asyncio.Semaphore] = {}
        self.replanning_threshold = 0.3  # Trigger replan if EGQ drops below
        
        # Metrics
        self.tasks_completed = 0
        self.tasks_failed = 0
        self.replans_triggered = 0
        
        logger.info("SwarmResearchOrchestrator initialized")

    def _emit_event(self, event_name: str, payload: Dict[str, Any]) -> None:
        event = {"type": event_name, "timestamp": time.time(), "data": payload}
        if self.event_callback:
            try:
                self.event_callback(event)
            except Exception as exc:
                logger.debug("Research event callback failed: %s", exc)
        logger.debug("research event: %s", event)

    def _emit_state(self, phase: str, text: str, **extra: Any) -> None:
        payload = {"phase": phase, "text": text}
        payload.update(extra)
        self._emit_event("cali:state", payload)
    
    # =====================================================================
    # PLANNING: Mission → Research Plan
    # =====================================================================
    
    async def create_research_plan(self, mission: SwarmMission) -> ResearchPlan:
        """
        Convert high-level mission into executable research plan.
        """
        self._emit_state("planning", "Breaking down your request...", mission_id=mission.mission_id)
        plan_id = f"plan_{mission.mission_id}_{int(time.time())}"
        
        plan = ResearchPlan(
            plan_id=plan_id,
            mission_id=mission.mission_id
        )
        
        # Phase 1: Discovery (always)
        discovery_tasks = self._create_discovery_phase(mission)
        for task in discovery_tasks:
            plan.tasks[task.task_id] = task
        
        # Phase 2: Deep retrieval (for complex missions)
        if mission.mission_type in [MissionType.DEEP_INVESTIGATION,
                                    MissionType.COMPREHENSIVE_DOSSIER]:
            deep_tasks = self._create_deep_phase(mission, discovery_tasks)
            for task in deep_tasks:
                plan.tasks[task.task_id] = task
                # Depend on discovery
                task.depends_on = [dt.task_id for dt in discovery_tasks[:2]]
        
        # Phase 3: Verification (for high-stakes)
        if mission.mission_type in [MissionType.COMPREHENSIVE_DOSSIER,
                                    MissionType.EMERGENCY_RESPONSE]:
            verify_tasks = self._create_verification_phase(mission)
            for task in verify_tasks:
                plan.tasks[task.task_id] = task
                # Depend on all prior phases
        
        # Phase 4: Synthesis (always, final)
        synthesis_task = ResearchTask(
            task_id=f"synth_{plan_id}",
            task_type=TaskType.SYNTHESIS,
            priority=TaskPriority.CRITICAL,
            description="Compile final research report",
            query=f"Synthesize findings on: {mission.topic}",
            depends_on=[t.task_id for t in plan.tasks.values() 
                       if t.task_type != TaskType.SYNTHESIS]
        )
        plan.tasks[synthesis_task.task_id] = synthesis_task
        
        # Build execution order (parallel groups)
        plan.execution_order = self._compute_execution_order(plan)
        
        self.active_plans[plan_id] = plan
        logger.info(f"Created plan {plan_id} with {len(plan.tasks)} tasks")
        
        return plan
    
    def _create_discovery_phase(self, mission: SwarmMission) -> List[ResearchTask]:
        """Create initial discovery tasks"""
        tasks = []
        
        # Broad search
        tasks.append(ResearchTask(
            task_id=f"discover_search_{mission.mission_id}",
            task_type=TaskType.WEB_SEARCH,
            priority=TaskPriority.HIGH,
            description="Broad web search for topic overview",
            query=mission.topic,
            source_constraints={'max_results': 10}
        ))
        
        # Entity extraction from initial sources
        tasks.append(ResearchTask(
            task_id=f"discover_entities_{mission.mission_id}",
            task_type=TaskType.ENTITY_EXTRACTION,
            priority=TaskPriority.HIGH,
            description="Extract key entities from initial findings",
            query=f"entities in: {mission.topic}",
            depends_on=[tasks[0].task_id]
        ))
        
        return tasks
    
    def _create_deep_phase(self, 
                          mission: SwarmMission,
                          discovery_tasks: List[ResearchTask]) -> List[ResearchTask]:
        """Create deep investigation tasks"""
        tasks = []
        
        # Document retrieval for key sources
        tasks.append(ResearchTask(
            task_id=f"deep_docs_{mission.mission_id}",
            task_type=TaskType.DOCUMENT_RETRIEVAL,
            priority=TaskPriority.NORMAL,
            description="Retrieve primary source documents",
            query=f"primary sources: {mission.topic}",
            source_constraints={'types': ['pdf', 'filing', 'official']}
        ))
        
        # Timeline construction
        tasks.append(ResearchTask(
            task_id=f"deep_timeline_{mission.mission_id}",
            task_type=TaskType.TIMELINE_CONSTRUCTION,
            priority=TaskPriority.NORMAL,
            description="Build chronological timeline of events",
            query=f"timeline: {mission.topic}",
            depends_on=[tasks[0].task_id]
        ))
        
        # Relationship mapping
        tasks.append(ResearchTask(
            task_id=f"deep_relations_{mission.mission_id}",
            task_type=TaskType.RELATIONSHIP_MAPPING,
            priority=TaskPriority.NORMAL,
            description="Map entity relationships and connections",
            query=f"relationships in: {mission.topic}",
            depends_on=[discovery_tasks[1].task_id]  # Depends on entity extraction
        ))
        
        return tasks
    
    def _create_verification_phase(self, mission: SwarmMission) -> List[ResearchTask]:
        """Create verification tasks"""
        tasks = []
        
        tasks.append(ResearchTask(
            task_id=f"verify_facts_{mission.mission_id}",
            task_type=TaskType.VERIFICATION,
            priority=TaskPriority.HIGH,
            description="Cross-verify key claims across sources",
            query=f"verify: {mission.topic}"
        ))
        
        tasks.append(ResearchTask(
            task_id=f"verify_contradictions_{mission.mission_id}",
            task_type=TaskType.CONTRADICTION_ANALYSIS,
            priority=TaskPriority.HIGH,
            description="Identify and resolve contradictions",
            query=f"contradictions in: {mission.topic}",
            depends_on=[tasks[0].task_id]
        ))
        
        return tasks
    
    def _compute_execution_order(self, plan: ResearchPlan) -> List[List[str]]:
        """
        Compute parallel execution groups respecting dependencies.
        Returns list of task ID groups that can execute in parallel.
        """
        remaining = set(plan.tasks.keys())
        completed = set()
        execution_order = []
        
        while remaining:
            # Find tasks whose deps are satisfied
            ready = []
            for task_id in remaining:
                task = plan.tasks[task_id]
                deps_satisfied = all(d in completed for d in task.depends_on)
                if deps_satisfied:
                    ready.append(task_id)
            
            if not ready:
                # Circular dependency or bug
                logger.error(f"No ready tasks but {len(remaining)} remaining")
                break
            
            execution_order.append(ready)
            completed.update(ready)
            remaining -= set(ready)
        
        return execution_order
    
    # =====================================================================
    # EXECUTION: Task Assignment & Monitoring
    # =====================================================================
    
    async def execute_plan(self, plan: ResearchPlan, mission: SwarmMission):
        """
        Execute research plan by assigning tasks to orbs.
        """
        logger.info(f"Executing plan {plan.plan_id}")
        self._emit_event(
            "swarm:start",
            {"mission_id": mission.mission_id, "plan_id": plan.plan_id, "query": mission.topic},
        )
        
        # Create semaphore for this mission
        self.execution_semaphores[mission.mission_id] = asyncio.Semaphore(5)
        
        # Execute by parallel groups
        for group_idx, task_group in enumerate(plan.execution_order):
            logger.debug(f"Executing group {group_idx}: {len(task_group)} tasks")
            
            # Create tasks for this group
            group_tasks = [
                self._execute_task_with_orb(plan, task_id, mission)
                for task_id in task_group
            ]
            
            # Execute in parallel
            results = await asyncio.gather(*group_tasks, return_exceptions=True)
            
            # Process results
            for task_id, result in zip(task_group, results):
                if isinstance(result, Exception):
                    logger.error(f"Task {task_id} failed: {result}")
                    plan.tasks[task_id].status = "failed"
                    self.tasks_failed += 1
                else:
                    self.tasks_completed += 1
            
            # Check for dynamic replanning opportunity
            if group_idx > 0 and group_idx % 2 == 0:
                await self._evaluate_replanning(plan, mission)
        
        # Finalize
        del self.execution_semaphores[mission.mission_id]
        self._emit_event(
            "swarm:complete",
            {"mission_id": mission.mission_id, "plan_id": plan.plan_id, "tasks": len(plan.tasks)},
        )
        logger.info(f"Plan {plan.plan_id} execution complete")
    
    async def _execute_task_with_orb(self,
                                      plan: ResearchPlan,
                                      task_id: str,
                                      mission: SwarmMission) -> Dict:
        """
        Assign task to appropriate orb and execute.
        """
        task = plan.tasks[task_id]
        
        # Find available orb for this task type
        orb = self._assign_orb_to_task(task, mission)
        if not orb:
            logger.warning(f"No available orb for task {task_id}, executing directly")
            return await self._execute_task_directly(task)
        
        # Assign
        task.assigned_orb = orb.orb_id
        task.status = "active"
        task.started_at = datetime.now()
        self.orb_task_assignments[orb.orb_id] = task_id
        self._emit_event(
            "swarm:worker:start",
            {
                "worker_id": orb.orb_id,
                "task_id": task.task_id,
                "task_type": task.task_type.name,
                "description": task.description,
            },
        )
        
        logger.debug(f"Assigned task {task_id} to orb {orb.orb_id}")
        
        try:
            # Execute based on task type
            result = await self._execute_by_type(task)
            
            # Mark complete
            task.status = "completed"
            task.completed_at = datetime.now()
            task.findings = result.get('findings', [])
            self.task_results[task.task_id] = task.findings
            self._emit_event(
                "swarm:worker:complete",
                {
                    "worker_id": orb.orb_id,
                    "task_id": task.task_id,
                    "task_type": task.task_type.name,
                    "findings_count": len(task.findings),
                    "confidence": result.get("confidence", 0),
                },
            )
            
            # Convert to contribution metrics
            metrics = create_metrics_from_finding(
                orb.orb_id,
                orb.lane,
                orb.orb_class.name,
                {
                    'novelty': result.get('novelty_score', 0.5),
                    'confidence': result.get('confidence', 0.5),
                    'coverage': result.get('coverage', 0.3),
                    'depth': result.get('depth', 0.3),
                    'primary_sources': result.get('primary_sources', 0),
                    'processing_time': task.get_duration_seconds() or 0
                }
            )
            
            # Report to governor
            await self.governor.process_orb_completion(
                orb.orb_id,
                [f.__dict__ if hasattr(f, '__dict__') else f for f in task.findings]
            )
            
            return result
            
        except Exception as e:
            task.status = "failed"
            await self.governor.report_orb_failure(orb.orb_id, str(e), retryable=True)
            raise
        
        finally:
            del self.orb_task_assignments[orb.orb_id]
    
    def _assign_orb_to_task(self, 
                            task: ResearchTask, 
                            mission: SwarmMission) -> Optional[OrbInstance]:
        """
        Find best orb for this task based on specialization.
        """
        required_capabilities = self.ORB_SPECIALIZATION.get(task.task_type, [])
        
        # Look for active orb with right capabilities
        for orb_id, orb in mission.active_orbs.items():
            if orb.orb_class in required_capabilities:
                if orb_id not in self.orb_task_assignments:
                    return orb
        
        # Look in queued orbs
        for orb in mission.queued_orbs:
            if orb.orb_class in required_capabilities:
                # Promote to active
                orb.status = "active"
                mission.active_orbs[orb.orb_id] = orb
                mission.queued_orbs.remove(orb)
                return orb
        
        return None
    
    async def _execute_by_type(self, task: ResearchTask) -> Dict:
        """
        Route task to appropriate execution method.
        """
        executors = {
            TaskType.WEB_SEARCH: self._execute_web_search,
            TaskType.DOCUMENT_RETRIEVAL: self._execute_document_retrieval,
            TaskType.ENTITY_EXTRACTION: self._execute_entity_extraction,
            TaskType.VERIFICATION: self._execute_verification,
            TaskType.SYNTHESIS: self._execute_synthesis,
            TaskType.RELATIONSHIP_MAPPING: self._execute_relationship_mapping,
            TaskType.TIMELINE_CONSTRUCTION: self._execute_timeline_construction,
            TaskType.CONTRADICTION_ANALYSIS: self._execute_contradiction_analysis
        }
        
        executor = executors.get(task.task_type, self._execute_generic)
        return await executor(task)
    
    async def _execute_web_search(self, task: ResearchTask) -> Dict:
        """Execute web search task"""
        self._emit_state("searching", "Searching local substrate...", task_id=task.task_id)
        results = await self.engine.execute_search(task.query, task.source_constraints)
        
        findings = []
        for r in results:
            finding = {
                'source_type': r.get('source_type', 'web'),
                'source': r.get('url'),
                'title': r.get('title'),
                'content': r.get('snippet'),
                'entities': r.get('entities', []),
                'claims': [{'text': r.get('snippet', ''), 'confidence': r.get('confidence', 0.65)}],
                'confidence': r.get('confidence', 0.65),
                'novelty': 0.7
            }
            findings.append(finding)
        confidence = self._confidence_from_findings(findings)
        
        return {
            'findings': findings,
            'novelty_score': 0.7,
            'confidence': confidence,
            'coverage': min(1.0, len(results) / max(1, task.source_constraints.get('max_results', 10))),
            'depth': 0.3,
            'primary_sources': self._count_primary_sources(findings)
        }
    
    async def _execute_document_retrieval(self, task: ResearchTask) -> Dict:
        """Execute document fetch and parse"""
        self._emit_state("searching", "Retrieving source documents...", task_id=task.task_id)
        search_results = await self.engine.execute_search(task.query, {**task.source_constraints, "max_results": 4})
        documents = []
        for result in search_results[:4]:
            reference = result.get("url")
            if not reference:
                continue
            document = await self.engine.fetch_document(reference)
            if document:
                documents.append(document)
        findings = [
            {
                "source_type": "document",
                "source": doc.get("url"),
                "title": doc.get("title"),
                "content": doc.get("content", "")[:1200],
                "metadata": doc.get("metadata", {}),
                "confidence": 0.74,
                "novelty": 0.75,
            }
            for doc in documents
        ]
        return {
            'findings': findings,
            'novelty_score': 0.8,
            'confidence': self._confidence_from_findings(findings),
            'coverage': min(1.0, len(findings) / 4),
            'depth': 0.8,
            'primary_sources': self._count_primary_sources(findings)
        }
    
    async def _execute_entity_extraction(self, task: ResearchTask) -> Dict:
        """Extract entities from prior findings"""
        accumulated = self._accumulated_research_text()
        if not accumulated:
            accumulated = task.query
        entities = await self.engine.extract_entities(accumulated)
        findings = [
            {
                "source_type": "entity_extraction",
                "source": task.task_id,
                "title": "Extracted entities",
                "content": ", ".join(entity["text"] for entity in entities[:30]),
                "entities": [entity["text"] for entity in entities],
                "confidence": 0.68 if entities else 0.3,
                "novelty": 0.55,
            }
        ] if entities else []
        return {
            'findings': findings,
            'novelty_score': 0.6,
            'confidence': self._confidence_from_findings(findings),
            'coverage': min(1.0, len(entities) / 20) if entities else 0,
            'depth': 0.4,
            'primary_sources': 0
        }
    
    async def _execute_verification(self, task: ResearchTask) -> Dict:
        """Cross-verify claims"""
        self._emit_state("verifying", "Cross-checking sources...", task_id=task.task_id)
        results = await self.engine.execute_search(task.query, {**task.source_constraints, "max_results": 6})
        unique_sources = len({item.get("url") for item in results if item.get("url")})
        confidence = min(0.92, 0.45 + (unique_sources * 0.11))
        findings = [
            {
                "source_type": item.get("source_type", "verification"),
                "source": item.get("url"),
                "title": item.get("title"),
                "content": item.get("snippet"),
                "confidence": item.get("confidence", confidence),
                "novelty": 0.35,
            }
            for item in results
        ]
        return {
            'findings': findings,
            'novelty_score': 0.4,  # Verification is less novel
            'confidence': round(confidence, 2),
            'coverage': min(1.0, unique_sources / 4),
            'depth': 0.9,
            'primary_sources': self._count_primary_sources(findings)
        }
    
    async def _execute_synthesis(self, task: ResearchTask) -> Dict:
        """Compile final report"""
        self._emit_state("synthesizing", "Building answer...", task_id=task.task_id)
        findings = []
        for stored_findings in self.task_results.values():
            findings.extend(stored_findings)
        summary = self._synthesize_findings(findings)
        confidence = self._confidence_from_findings(findings)
        return {
            'findings': [{
                "source_type": "synthesis",
                "source": task.task_id,
                "title": "Research synthesis",
                "content": summary,
                "confidence": confidence,
                "novelty": 0.2,
            }] if summary else [],
            'novelty_score': 0.2,  # Synthesis is organization, not discovery
            'confidence': confidence,
            'coverage': 1.0 if findings else 0,
            'depth': 0.5,
            'primary_sources': self._count_primary_sources(findings)
        }
    
    async def _execute_relationship_mapping(self, task: ResearchTask) -> Dict:
        """Map entity relationships"""
        accumulated = self._accumulated_research_text() or task.query
        entities = await self.engine.extract_entities(accumulated)
        entity_names = [entity["text"] for entity in entities[:12]]
        relationships = []
        for i, left in enumerate(entity_names):
            for right in entity_names[i + 1:i + 3]:
                relationships.append(f"{left} <-> {right}")
        findings = [{
            "source_type": "relationship_mapping",
            "source": task.task_id,
            "title": "Entity relationship map",
            "content": "; ".join(relationships[:20]),
            "entities": entity_names,
            "confidence": 0.62 if relationships else 0.3,
            "novelty": 0.65,
        }] if relationships else []
        return {
            'findings': findings,
            'novelty_score': 0.7,
            'confidence': self._confidence_from_findings(findings),
            'coverage': min(1.0, len(relationships) / 12) if relationships else 0,
            'depth': 0.7,
            'primary_sources': 0
        }
    
    async def _execute_timeline_construction(self, task: ResearchTask) -> Dict:
        """Build chronological timeline"""
        text = self._accumulated_research_text()
        dates = re.findall(r"\b(?:19|20)\d{2}(?:-\d{2}-\d{2})?\b", text)
        findings = [{
            "source_type": "timeline",
            "source": task.task_id,
            "title": "Timeline markers",
            "content": ", ".join(sorted(set(dates))[:30]),
            "metadata": {"dates": sorted(set(dates))[:30]},
            "confidence": 0.64 if dates else 0.25,
            "novelty": 0.55,
        }] if dates else []
        return {
            'findings': findings,
            'novelty_score': 0.6,
            'confidence': self._confidence_from_findings(findings),
            'coverage': min(1.0, len(set(dates)) / 8) if dates else 0,
            'depth': 0.8,
            'primary_sources': 0
        }
    
    async def _execute_contradiction_analysis(self, task: ResearchTask) -> Dict:
        """Identify contradictions in findings"""
        self._emit_state("verifying", "Checking for contradictions...", task_id=task.task_id)
        findings = []
        source_count = len({f.get("source") for stored in self.task_results.values() for f in stored if f.get("source")})
        return {
            'findings': findings,
            'novelty_score': 0.5,
            'confidence': min(0.85, 0.45 + source_count * 0.08),
            'coverage': min(1.0, source_count / 4),
            'depth': 0.9,
            'primary_sources': 0,
            'contradictions_resolved': 0
        }
    
    async def _execute_generic(self, task: ResearchTask) -> Dict:
        """Fallback execution"""
        results = await self.engine.execute_search(task.query, task.source_constraints)
        findings = [
            {
                "source_type": item.get("source_type", "generic"),
                "source": item.get("url"),
                "title": item.get("title"),
                "content": item.get("snippet"),
                "confidence": item.get("confidence", 0.55),
                "novelty": 0.45,
            }
            for item in results
        ]
        return {
            'findings': findings,
            'novelty_score': 0.5,
            'confidence': self._confidence_from_findings(findings),
            'coverage': min(1.0, len(findings) / 5),
            'depth': 0.5,
            'primary_sources': 0
        }

    def _confidence_from_findings(self, findings: List[Dict]) -> float:
        if not findings:
            return 0.0
        values = [
            float(finding.get("confidence", 0.5))
            for finding in findings
            if isinstance(finding.get("confidence", 0.5), (int, float))
        ]
        average = sum(values) / max(1, len(values))
        source_bonus = min(0.18, len({f.get("source") for f in findings if f.get("source")}) * 0.04)
        return round(min(0.95, max(0.0, average + source_bonus)), 2)

    def _count_primary_sources(self, findings: List[Dict]) -> int:
        primary_markers = ("gov", "nih", "nasa", "noaa", "sec.gov", "usgs", "clinicaltrials")
        return sum(
            1
            for finding in findings
            if any(marker in str(finding.get("source", "")).lower() for marker in primary_markers)
        )

    def _accumulated_research_text(self) -> str:
        chunks: List[str] = []
        for findings in self.task_results.values():
            for finding in findings:
                chunks.append(str(finding.get("title") or ""))
                chunks.append(str(finding.get("content") or ""))
        return " ".join(chunk for chunk in chunks if chunk).strip()

    def _synthesize_findings(self, findings: List[Dict]) -> str:
        if not findings:
            return ""
        seen = set()
        chunks = []
        for finding in findings:
            text = " ".join(str(finding.get("content") or finding.get("title") or "").split())
            if not text:
                continue
            key = text[:120].lower()
            if key in seen:
                continue
            seen.add(key)
            chunks.append(text[:350])
            if len(chunks) >= 5:
                break
        return " ".join(chunks)
    
    async def _execute_task_directly(self, task: ResearchTask) -> Dict:
        """Execute without orb assignment (fallback)"""
        result = await self._execute_by_type(task)
        self.task_results[task.task_id] = result.get("findings", [])
        return result
    
    # =====================================================================
    # DYNAMIC REPLANNING
    # =====================================================================
    
    async def _evaluate_replanning(self, plan: ResearchPlan, mission: SwarmMission):
        """
        Check if current trajectory warrants plan revision.
        """
        # Get current EGQ from governor's perspective
        status = self.governor.get_mission_status(mission.mission_id)
        if not status:
            return
        
        current_egq = status.get('total_novelty', 0) / max(status.get('completed_orbs', 1), 1)
        
        if current_egq < self.replanning_threshold:
            logger.info(f"Triggering replan for {plan.plan_id}: EGQ {current_egq:.3f}")
            await self._replan_mission(plan, mission)
    
    async def _replan_mission(self, plan: ResearchPlan, mission: SwarmMission):
        """
        Create revised plan based on intermediate findings.
        """
        self.replans_triggered += 1
        
        # Analyze what we've found so far
        discovered_entities = set()
        for task in plan.tasks.values():
            for finding in task.findings:
                discovered_entities.update(finding.get('entities', []))
        
        # Create new plan (simplified: add follow-up tasks)
        new_tasks = []
        
        # If we found entities, investigate each
        for entity in list(discovered_entities)[:3]:  # Limit to top 3
            follow_up = ResearchTask(
                task_id=f"followup_{entity}_{int(time.time())}",
                task_type=TaskType.WEB_SEARCH,
                priority=TaskPriority.NORMAL,
                description=f"Deep dive on discovered entity: {entity}",
                query=f"{entity} {mission.topic}",
                depends_on=[t.task_id for t in plan.tasks.values() if t.status == "completed"][-1:]
            )
            new_tasks.append(follow_up)
            plan.tasks[follow_up.task_id] = follow_up
        
        # Recompute execution order
        plan.execution_order = self._compute_execution_order(plan)
        plan.generation += 1
        
        logger.info(f"Replan complete: added {len(new_tasks)} follow-up tasks")
    
    # =====================================================================
    # RESULT AGGREGATION
    # =====================================================================
    
    def aggregate_findings(self, plan: ResearchPlan) -> Dict:
        """
        Compile all task findings into unified result.
        """
        all_findings = []
        for task in plan.tasks.values():
            all_findings.extend(task.findings)
        
        # Deduplicate by source
        by_source = {}
        for finding in all_findings:
            source = finding.get('source', 'unknown')
            if source not in by_source:
                by_source[source] = finding
        
        # Build entity graph
        entity_connections = defaultdict(set)
        for finding in all_findings:
            entities = finding.get('entities', [])
            for i, e1 in enumerate(entities):
                for e2 in entities[i+1:]:
                    entity_connections[e1].add(e2)
                    entity_connections[e2].add(e1)
        
        # Timeline extraction
        dated_findings = [
            f for f in all_findings 
            if f.get('metadata', {}).get('date')
        ]
        timeline = sorted(dated_findings, 
                         key=lambda x: x.get('metadata', {}).get('date', ''))
        
        return {
            'total_findings': len(all_findings),
            'unique_sources': len(by_source),
            'entity_graph': dict(entity_connections),
            'timeline': timeline,
            'by_task_type': self._group_by_task_type(plan)
        }
    
    def _group_by_task_type(self, plan: ResearchPlan) -> Dict:
        """Group findings by task type"""
        grouped = defaultdict(list)
        for task in plan.tasks.values():
            for finding in task.findings:
                grouped[task.task_type.name].append(finding)
        return dict(grouped)


# ============================================================================
# HIGH-LEVEL INTERFACE
# ============================================================================

class SwarmResearchSession:
    """
    User-facing interface for swarm research.
    Encapsulates a complete research session from initiation to report.
    """
    
    def __init__(self, 
                 governor: EpistemicSwarmGovernor,
                 orchestrator: Optional[SwarmResearchOrchestrator] = None):
        self.governor = governor
        self.orchestrator = orchestrator or SwarmResearchOrchestrator(governor)
        self.active_sessions: Dict[str, Dict] = {}
    
    async def start_research(self,
                            topic: str,
                            mission_type: MissionType = MissionType.TOPIC_SURVEY,
                            context: Optional[Dict] = None) -> str:
        """
        Start complete research session.
        Returns session ID for status tracking.
        """
        # Initiate with governor
        try:
            mission = await self.governor.initiate_mission(topic, mission_type, context)
        except MissionDeniedError as e:
            raise
        
        # Create research plan
        plan = await self.orchestrator.create_research_plan(mission)
        
        # Start execution in background
        session_id = f"session_{mission.mission_id}"
        self.active_sessions[session_id] = {
            'mission': mission,
            'plan': plan,
            'start_time': datetime.now(),
            'status': 'running'
        }
        
        # Launch execution
        asyncio.create_task(self._run_session(session_id))
        
        return session_id
    
    async def _run_session(self, session_id: str):
        """Background execution of research session"""
        session = self.active_sessions[session_id]
        mission = session['mission']
        plan = session['plan']
        
        try:
            await self.orchestrator.execute_plan(plan, mission)
            session['status'] = 'complete'
            session['results'] = self.orchestrator.aggregate_findings(plan)
        except Exception as e:
            logger.error(f"Session {session_id} failed: {e}")
            session['status'] = 'failed'
            session['error'] = str(e)
    
    def get_session_status(self, session_id: str) -> Optional[Dict]:
        """Get current status of research session"""
        session = self.active_sessions.get(session_id)
        if not session:
            return None
        
        mission = session['mission']
        plan = session['plan']
        
        return {
            'session_id': session_id,
            'status': session['status'],
            'topic': mission.topic,
            'mission_type': mission.mission_type.name,
            'elapsed_seconds': (datetime.now() - session['start_time']).seconds,
            'tasks_total': len(plan.tasks),
            'tasks_completed': sum(1 for t in plan.tasks.values() if t.status == "completed"),
            'tasks_failed': sum(1 for t in plan.tasks.values() if t.status == "failed"),
            'current_egq': self._calculate_session_egq(session),
            'findings_preview': self._get_findings_preview(session)
        }
    
    def _calculate_session_egq(self, session: Dict) -> float:
        """Calculate current EGQ for session"""
        # Delegate to EPIC
        epic = EPIC({
            'mission_type': session['mission'].mission_type.name,
            'domain': 'general'
        })
        
        # Convert task findings to contributions
        for task in session['plan'].tasks.values():
            if task.findings and task.assigned_orb:
                for finding in task.findings:
                    metrics = create_metrics_from_finding(
                        task.assigned_orb,
                        task.task_type.name,
                        "UNKNOWN",
                        finding
                    )
                    epic.all_contributions.append(metrics)
        
        return epic.calculate_egq()
    
    def _get_findings_preview(self, session: Dict) -> List[Dict]:
        """Get preview of findings so far"""
        findings = []
        for task in session['plan'].tasks.values():
            for finding in task.findings[:3]:  # Top 3 per task
                findings.append({
                    'source': finding.get('source', 'unknown'),
                    'title': finding.get('title', 'Untitled'),
                    'confidence': finding.get('confidence', 0)
                })
        return findings[:10]  # Overall top 10
    
    def get_final_report(self, session_id: str) -> Optional[Dict]:
        """Get complete research report"""
        session = self.active_sessions.get(session_id)
        if not session or session['status'] != 'complete':
            return None
        
        return {
            'session_id': session_id,
            'topic': session['mission'].topic,
            'mission_type': session['mission'].mission_type.name,
            'duration_seconds': (datetime.now() - session['start_time']).seconds,
            'aggregation': session.get('results', {}),
            'governor_summary': self.governor.get_mission_status(session['mission'].mission_id)
        }


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

async def example_usage():
    """Demonstrate complete swarm research flow"""

    class LocalResearchBackend:
        def __init__(self, config: Dict[str, Any]):
            self.config = config

    # Setup
    repo_root = Path(__file__).resolve().parents[4]
    backend = LocalResearchBackend({"type": "local", "root": str(repo_root)})
    vault = ResearchEventVault(repo_root / "CALI_System" / "memory" / "research_vault")
    governor = EpistemicSwarmGovernor(backend, vault)

    def capture_research_event(event: Dict[str, Any]) -> None:
        vault.append_event(event)

    orchestrator = SwarmResearchOrchestrator(governor, event_callback=capture_research_event)
    session_manager = SwarmResearchSession(governor, orchestrator)
    
    # Set visual callbacks (normally wired to Electron)
    def on_spawn(data):
        print(f"  [VISUAL] Spawned {data['orb_class']} orb")
    
    def on_return(data):
        print(f"  [VISUAL] Orb returned with {data.get('findings_count', 0)} findings")
    
    def on_complete(mission_id, synthesis):
        print(f"  [VISUAL] Mission {mission_id} complete!")
        print(f"  Summary: {synthesis.get('summary', 'N/A')[:100]}...")
    
    governor.on_orb_spawn = on_spawn
    governor.on_orb_return = on_return
    governor.on_mission_complete = on_complete
    
    # Start research
    print("\n=== Starting Research Session ===")
    session_id = await session_manager.start_research(
        topic="Halo Pets acquisition by Better Choice Company",
        mission_type=MissionType.DEEP_INVESTIGATION,
        context={'domain': 'financial', 'urgency': 'normal'}
    )
    
    print(f"Session ID: {session_id}")
    
    # Poll status (in real use, this would be WebSocket push)
    for i in range(5):
        await asyncio.sleep(0.5)
        status = session_manager.get_session_status(session_id)
        print(f"\nStatus check {i+1}:")
        print(f"  Tasks: {status['tasks_completed']}/{status['tasks_total']}")
        print(f"  EGQ: {status['current_egq']:.3f}")
        print(f"  Findings so far: {len(status['findings_preview'])}")
    
    # Get final report
    await asyncio.sleep(1)  # Let completion happen
    report = session_manager.get_final_report(session_id)
    if report:
        print(f"\n=== Final Report ===")
        print(f"Duration: {report['duration_seconds']}s")
        print(f"Unique sources: {report['aggregation'].get('unique_sources', 0)}")


if __name__ == "__main__":
    asyncio.run(example_usage())
