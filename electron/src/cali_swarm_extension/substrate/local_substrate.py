import hashlib
import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


class LocalSwarmSubstrate:
    """Local-first shared substrate for research cache, task mesh, and promoted knowledge."""

    def __init__(self, system_root: Path):
        self.system_root = Path(system_root).expanduser().resolve()
        self.swarm_dir = self.system_root / "swarm"
        self.swarm_dir.mkdir(parents=True, exist_ok=True)
        self.db_path = self.swarm_dir / "substrate.db"
        self._lock = threading.Lock()
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30, check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.row_factory = sqlite3.Row
        return conn

    def _init_schema(self) -> None:
        with self._lock:
            with self._connect() as conn:
                conn.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS research_cache (
                        query_hash TEXT PRIMARY KEY,
                        query_text TEXT NOT NULL,
                        domains_json TEXT NOT NULL,
                        result_json TEXT NOT NULL,
                        quality_score REAL NOT NULL DEFAULT 0,
                        hit_count INTEGER NOT NULL DEFAULT 0,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL,
                        last_hit_at REAL
                    );

                    CREATE TABLE IF NOT EXISTS promoted_knowledge (
                        knowledge_key TEXT PRIMARY KEY,
                        query_hash TEXT NOT NULL,
                        summary TEXT,
                        data_json TEXT NOT NULL,
                        score REAL NOT NULL DEFAULT 0,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    );

                    CREATE TABLE IF NOT EXISTS task_mesh (
                        task_id TEXT PRIMARY KEY,
                        capability TEXT NOT NULL,
                        payload_json TEXT NOT NULL,
                        priority INTEGER NOT NULL DEFAULT 5,
                        status TEXT NOT NULL DEFAULT 'pending',
                        assigned_to TEXT,
                        result_json TEXT,
                        created_at REAL NOT NULL,
                        updated_at REAL NOT NULL
                    );
                    """
                )

    def _query_hash(self, query: str, domains: Optional[List[str]] = None) -> str:
        normalized_query = " ".join(str(query or "").strip().lower().split())
        normalized_domains = sorted(
            [str(domain).strip().lower() for domain in (domains or []) if str(domain).strip()]
        )
        seed = f"{normalized_query}|{'|'.join(normalized_domains)}"
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()

    def _safe_json(self, payload: Any) -> str:
        return json.dumps(payload, default=str, ensure_ascii=False)

    def _estimate_quality_score(self, result: Dict[str, Any]) -> float:
        if not isinstance(result, dict):
            return 0.0
        synthesis = result.get("research_synthesis")
        if isinstance(synthesis, dict) and synthesis.get("error"):
            return 0.0
        if isinstance(synthesis, dict):
            confidence = synthesis.get("confidence")
            if isinstance(confidence, (int, float)):
                return float(max(0.0, min(1.0, confidence)))
        references = result.get("references") or result.get("sources") or []
        if isinstance(references, list) and references:
            return min(1.0, 0.45 + (len(references) * 0.08))
        return 0.35

    def lookup_research(
        self, query: str, domains: Optional[List[str]] = None, max_age_seconds: int = 86400
    ) -> Optional[Dict[str, Any]]:
        now = time.time()
        query_hash = self._query_hash(query, domains)
        min_timestamp = now - max(1, int(max_age_seconds))

        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT result_json, quality_score, hit_count, updated_at
                    FROM research_cache
                    WHERE query_hash = ? AND updated_at >= ?
                    """,
                    (query_hash, min_timestamp),
                ).fetchone()
                if not row:
                    return None

                conn.execute(
                    """
                    UPDATE research_cache
                    SET hit_count = hit_count + 1, last_hit_at = ?
                    WHERE query_hash = ?
                    """,
                    (now, query_hash),
                )
                conn.commit()

        try:
            payload = json.loads(row["result_json"])
        except Exception:
            return None

        if not isinstance(payload, dict):
            return {"payload": payload}

        payload["_swarm_cache"] = {
            "query_hash": query_hash,
            "quality_score": row["quality_score"],
            "hit_count": row["hit_count"] + 1,
            "updated_at": row["updated_at"],
        }
        return payload

    def store_research(
        self, query: str, domains: Optional[List[str]], result: Dict[str, Any]
    ) -> str:
        now = time.time()
        query_hash = self._query_hash(query, domains)
        quality = self._estimate_quality_score(result)
        domains_json = self._safe_json(domains or [])
        result_json = self._safe_json(result)

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO research_cache (
                        query_hash, query_text, domains_json, result_json,
                        quality_score, hit_count, created_at, updated_at, last_hit_at
                    ) VALUES (?, ?, ?, ?, ?, 0, ?, ?, NULL)
                    ON CONFLICT(query_hash) DO UPDATE SET
                        result_json = excluded.result_json,
                        domains_json = excluded.domains_json,
                        quality_score = excluded.quality_score,
                        updated_at = excluded.updated_at
                    """,
                    (query_hash, query, domains_json, result_json, quality, now, now),
                )
                conn.commit()

        if quality >= 0.75:
            summary = ""
            if isinstance(result, dict):
                summary = str(result.get("voice_response") or result.get("summary") or "").strip()
            self.promote_knowledge(
                query_hash=query_hash,
                summary=summary or f"Research result for: {query}",
                payload=result,
                score=quality,
            )

        return query_hash

    def promote_knowledge(
        self, query_hash: str, summary: str, payload: Dict[str, Any], score: float
    ) -> str:
        now = time.time()
        key_seed = f"{query_hash}|{summary[:120]}|{score:.4f}"
        knowledge_key = hashlib.sha256(key_seed.encode("utf-8")).hexdigest()[:24]

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO promoted_knowledge (
                        knowledge_key, query_hash, summary, data_json, score, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(knowledge_key) DO UPDATE SET
                        summary = excluded.summary,
                        data_json = excluded.data_json,
                        score = excluded.score,
                        updated_at = excluded.updated_at
                    """,
                    (
                        knowledge_key,
                        query_hash,
                        summary,
                        self._safe_json(payload),
                        float(max(0.0, min(1.0, score))),
                        now,
                        now,
                    ),
                )
                conn.commit()
        return knowledge_key

    def publish_task(
        self, payload: Dict[str, Any], capability: str = "general", priority: int = 5
    ) -> str:
        now = time.time()
        seed = self._safe_json(payload) + f"|{capability}|{now}"
        task_id = hashlib.sha256(seed.encode("utf-8")).hexdigest()[:24]

        with self._lock:
            with self._connect() as conn:
                conn.execute(
                    """
                    INSERT INTO task_mesh (
                        task_id, capability, payload_json, priority,
                        status, assigned_to, result_json, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, 'pending', NULL, NULL, ?, ?)
                    """,
                    (task_id, capability, self._safe_json(payload), int(priority), now, now),
                )
                conn.commit()
        return task_id

    def claim_task(self, worker_id: str, capability: str = "general") -> Optional[Dict[str, Any]]:
        now = time.time()
        with self._lock:
            with self._connect() as conn:
                row = conn.execute(
                    """
                    SELECT task_id, capability, payload_json, priority, status, assigned_to, created_at
                    FROM task_mesh
                    WHERE status = 'pending' AND (capability = ? OR capability = 'general')
                    ORDER BY priority ASC, created_at ASC
                    LIMIT 1
                    """,
                    (capability,),
                ).fetchone()
                if not row:
                    return None

                conn.execute(
                    """
                    UPDATE task_mesh
                    SET status = 'active', assigned_to = ?, updated_at = ?
                    WHERE task_id = ? AND status = 'pending'
                    """,
                    (worker_id, now, row["task_id"]),
                )
                conn.commit()

        try:
            payload = json.loads(row["payload_json"])
        except Exception:
            payload = {"raw_payload": row["payload_json"]}

        return {
            "task_id": row["task_id"],
            "capability": row["capability"],
            "priority": row["priority"],
            "payload": payload,
            "assigned_to": worker_id,
            "created_at": row["created_at"],
        }

    def complete_task(self, task_id: str, result: Optional[Dict[str, Any]] = None) -> bool:
        with self._lock:
            with self._connect() as conn:
                cursor = conn.execute(
                    """
                    UPDATE task_mesh
                    SET status = 'completed', result_json = ?, updated_at = ?
                    WHERE task_id = ? AND status IN ('pending', 'active')
                    """,
                    (self._safe_json(result or {}), time.time(), task_id),
                )
                conn.commit()
                return cursor.rowcount > 0

    def get_status(self) -> Dict[str, Any]:
        with self._lock:
            with self._connect() as conn:
                research_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM research_cache"
                ).fetchone()["count"]
                promoted_count = conn.execute(
                    "SELECT COUNT(*) AS count FROM promoted_knowledge"
                ).fetchone()["count"]
                pending_tasks = conn.execute(
                    "SELECT COUNT(*) AS count FROM task_mesh WHERE status = 'pending'"
                ).fetchone()["count"]
                active_tasks = conn.execute(
                    "SELECT COUNT(*) AS count FROM task_mesh WHERE status = 'active'"
                ).fetchone()["count"]

        return {
            "db_path": str(self.db_path),
            "research_cache_entries": int(research_count),
            "promoted_knowledge_entries": int(promoted_count),
            "pending_tasks": int(pending_tasks),
            "active_tasks": int(active_tasks),
        }

