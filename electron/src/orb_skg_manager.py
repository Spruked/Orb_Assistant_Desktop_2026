# ucm_4_core/cali/orb_skg_manager.py
"""
SKG Manager with Dynamic Rebuild & Edge Optimization
Prevents performance degradation under high-frequency orb operations
"""

import asyncio
import time
import psutil
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass
from datetime import datetime, timedelta
import threading
import queue
import numpy as np

from vault_logic_system_template.seed_vault import MasterSeedVault
from worker_forge.forge_engine import SKGForgeEngine
from ucm_4_core.ecm.epistemic_convergence import EpistemicConvergenceMatrix


@dataclass
class SKGHealthMetrics:
    """Real-time performance indicators"""

    query_latency_ms: float
    memory_usage_mb: float
    fragmentation_ratio: float
    write_queue_depth: int
    last_rebuild_timestamp: float
    rebuild_count: int

    def is_degraded(self) -> bool:
        """Determine if SKG needs rebuild"""
        return (
            self.query_latency_ms > 150  # 150ms threshold
            or self.memory_usage_mb > 500  # 500MB threshold
            or self.fragmentation_ratio > 0.6  # 60% fragmentation
            or self.write_queue_depth > 100  # 100 pending writes
        )


class SKGRebuildEngine:
    """
    Handles dynamic SKG rebuilds during orb operations
    Uses ECM for intelligent reorganization
    Implements "edge cutter" optimizations for CPU-only environment
    """

    def __init__(self, vault_path: str, worker_id: str):
        self.vault = MasterSeedVault(vault_path)
        self.forge = SKGForgeEngine(worker_id=worker_id)
        self.ecm = EpistemicConvergenceMatrix(vault_path)

        # Rebuild state
        self.is_rebuilding = False
        self.rebuild_lock = asyncio.Lock()
        self.last_rebuild = time.time()
        self.rebuild_interval = 3600  # Minimum 1 hour between rebuilds

        # Performance monitoring
        self.metrics = SKGHealthMetrics(
            query_latency_ms=0,
            memory_usage_mb=0,
            fragmentation_ratio=0,
            write_queue_depth=0,
            last_rebuild_timestamp=0,
            rebuild_count=0,
        )

        # Emergency cache for continuity during rebuild
        self.emergency_cache = queue.Queue(maxsize=1000)

        # Rebuild thresholds (dynamically adjusted)
        self.thresholds = {
            "latency_threshold_ms": 150,
            "memory_threshold_mb": 500,
            "fragmentation_threshold": 0.6,
            "edge_cpu_threshold": 75,  # CPU usage % for edge cutter mode
        }

        # Start monitoring thread
        self.monitor_thread = threading.Thread(
            target=self._continuous_monitoring, daemon=True
        )
        self.monitor_thread.start()

    def _continuous_monitoring(self):
        """Background thread monitoring SKG health"""
        while True:
            try:
                self._update_metrics()

                if self.metrics.is_degraded() and not self.is_rebuilding:
                    if time.time() - self.last_rebuild > self.rebuild_interval:
                        # Trigger async rebuild
                        asyncio.run_coroutine_threadsafe(
                            self.trigger_rebuild(), asyncio.get_event_loop()
                        )

                time.sleep(30)  # Check every 30 seconds
            except Exception as e:
                print(f"⚠️ Monitor thread error: {e}")
                time.sleep(60)

    def _update_metrics(self):
        """Update performance metrics"""
        # Measure query latency
        start = time.time()
        try:
            probe = self.forge.recall_vault_memory(domain="test", key="test")
            if asyncio.iscoroutine(probe):
                try:
                    asyncio.run(probe)
                except RuntimeError:
                    probe.close()
            self.metrics.query_latency_ms = (time.time() - start) * 1000
        except:
            self.metrics.query_latency_ms = 999

        # Memory usage
        process = psutil.Process()
        self.metrics.memory_usage_mb = process.memory_info().rss / 1024 / 1024

        # Fragmentation (estimated from forge engine stats)
        self.metrics.fragmentation_ratio = self.forge.get_fragmentation_ratio()

        # Write queue depth
        self.metrics.write_queue_depth = self.forge.get_write_queue_depth()

        # Update last rebuild timestamp
        self.metrics.last_rebuild_timestamp = self.last_rebuild

    async def trigger_rebuild(self, reason: str = "auto_degraded"):
        """
        Trigger SKG rebuild with ECM-driven reorganization
        Implements edge cutter optimizations
        """
        if self.is_rebuilding:
            print("⚠️ Rebuild already in progress")
            return

        async with self.rebuild_lock:
            self.is_rebuilding = True
            self.metrics.rebuild_count += 1

            print(f"🔄 Starting SKG rebuild: {reason}")
            print(f"   Current metrics: {self.metrics}")

            try:
                # Phase 1: Emergency cache activation
                await self._activate_emergency_cache()

                # Phase 2: ECM-driven reorganization
                reorganized_data = await self._ecm_reorganize_skg()

                # Phase 3: Edge cutter optimization (CPU-only)
                optimized_data = await self._edge_cutter_optimize(reorganized_data)

                # Phase 4: Atomic swap
                await self._atomic_skg_swap(optimized_data)

                # Phase 5: Cache flush
                await self._flush_emergency_cache()

                self.last_rebuild = time.time()
                print("✅ Rebuild completed successfully")

            except Exception as e:
                print(f"❌ Rebuild failed: {e}")
                await self._rollback_rebuild()
                raise

            finally:
                self.is_rebuilding = False

    async def _activate_emergency_cache(self):
        """Store recent high-priority data in memory cache"""
        print("💾 Activating emergency cache")

        # Get recent interactions (last 5 minutes)
        recent_cutoff = time.time() - 300
        recent_data = await self.forge.recall_vault_memory(
            domain="orb_interactions", key="recent"
        )

        if recent_data:
            for item in recent_data:
                if item["timestamp"] > recent_cutoff:
                    self.emergency_cache.put(item)

        # Start async cache writer
        asyncio.create_task(self._cache_writer_loop())

    async def _cache_writer_loop(self):
        """Continuously write from cache to SKG during rebuild"""
        while self.is_rebuilding:
            try:
                item = self.emergency_cache.get(timeout=1)
                await self.forge.forge_skg_body(
                    data=item, domain="orb_interactions", priority="high"
                )
            except queue.Empty:
                await asyncio.sleep(0.1)
            except Exception as e:
                print(f"⚠️ Cache write error: {e}")

    async def _ecm_reorganize_skg(self) -> Dict[str, Any]:
        """
        Use ECM to intelligently reorganize knowledge graph
        Groups related concepts, prioritizes frequent access patterns
        """
        print("🧠 ECM-driven SKG reorganization")

        # Extract all orb-related data
        all_interactions = await self.forge.recall_vault_memory(
            domain="orb_interactions", key="all"
        )

        if not all_interactions:
            return {}

        # Create convergence input for reorganization
        convergence_input = {
            "interaction_patterns": all_interactions,
            "temporal_clusters": self._cluster_by_temporality(all_interactions),
            "contextual_clusters": self._cluster_by_context(all_interactions),
            "access_frequency": self._calculate_access_frequency(all_interactions),
        }

        # ECM convergence for organization strategy
        reorganization_plan = await self.ecm.converge(
            input_modality="knowledge_optimization",
            raw_input=convergence_input,
            worker_context=self.forge.get_worker_skg(),
        )

        # Execute reorganization
        reorganized = {}
        for cluster_id, cluster_data in reorganization_plan.get("clusters", {}).items():
            reorganized[cluster_id] = {
                "data": cluster_data["items"],
                "priority": cluster_data["access_frequency"],
                "retention_policy": cluster_data["temporal_relevance"],
            }

        return reorganized

    def _cluster_by_temporality(self, interactions: List[Dict]) -> Dict:
        """Group interactions by time-based relevance"""
        now = time.time()
        clusters = {
            "hot": [],  # Last 1 hour
            "warm": [],  # Last 24 hours
            "cold": [],  # Last 7 days
            "archive": [],  # Older
        }

        for item in interactions:
            age = now - item.get("timestamp", 0)

            if age < 3600:
                clusters["hot"].append(item)
            elif age < 86400:
                clusters["warm"].append(item)
            elif age < 604800:
                clusters["cold"].append(item)
            else:
                clusters["archive"].append(item)

        return clusters

    def _cluster_by_context(self, interactions: List[Dict]) -> Dict:
        """Group by context (e.g., coding, browsing, etc.)"""
        clusters = {}

        for item in interactions:
            ctx = item.get("context", {}).get("page_context", "general")
            if ctx not in clusters:
                clusters[ctx] = []
            clusters[ctx].append(item)

        return clusters

    def _calculate_access_frequency(self, interactions: List[Dict]) -> Dict:
        """Calculate how often each data type is accessed"""
        frequency = {}

        for item in interactions:
            data_type = item.get("type", "general")
            frequency[data_type] = frequency.get(data_type, 0) + 1

        return frequency

    async def _edge_cutter_optimize(self, reorganized_data: Dict) -> Dict:
        """
        Edge cutter optimization for CPU-only, resource-constrained environment
        Reduces computation, prioritizes hot data
        """
        print("⚡ Edge cutter optimization (CPU-only mode)")

        optimized = {}
        total_items = sum(len(cluster["data"]) for cluster in reorganized_data.values())

        # CPU load check
        cpu_percent = psutil.cpu_percent(interval=1)
        if cpu_percent > self.thresholds["edge_cpu_threshold"]:
            print(f"   High CPU detected: {cpu_percent}% - Aggressive optimization")
            compression_factor = 0.5  # Compress more
        else:
            compression_factor = 0.8  # Preserve more data

        # Optimize each cluster
        for cluster_id, cluster in reorganized_data.items():
            # Priority-based filtering
            priority = cluster.get("priority", 0)

            if cluster_id == "hot":
                # Keep 100% of hot data (last hour)
                keep_ratio = 1.0
                storage_format = "memory_optimized"  # Fast access
            elif cluster_id == "warm":
                # Keep 80% of warm data
                keep_ratio = 0.8 * compression_factor
                storage_format = "balanced"
            elif cluster_id == "cold":
                # Keep 50% of cold data
                keep_ratio = 0.5 * compression_factor
                storage_format = "storage_optimized"
            else:  # archive
                # Keep 20% of archive, compress heavily
                keep_ratio = 0.2 * compression_factor
                storage_format = "compressed"

            # Filter and optimize data
            data = cluster["data"]
            if len(data) > 100:
                # Sort by importance score (access frequency + recency)
                data.sort(key=lambda x: self._importance_score(x), reverse=True)
                data = data[: int(len(data) * keep_ratio)]

            optimized[cluster_id] = {
                "data": data,
                "format": storage_format,
                "estimated_load_time": len(data) * 0.1,  # ms per item
            }

        return optimized

    def _importance_score(self, item: Dict) -> float:
        """Calculate importance score for prioritization"""
        now = time.time()
        age = now - item.get("timestamp", 0)

        # Recency weight (exponential decay)
        recency_score = np.exp(-age / 86400)  # 24-hour half-life

        # Access frequency weight
        freq_score = item.get("access_count", 1) / 10

        # Contextual relevance weight
        context_bonus = (
            2.0 if item.get("context", {}).get("is_assistance_context") else 1.0
        )

        return recency_score * freq_score * context_bonus

    async def _atomic_skg_swap(self, optimized_data: Dict):
        """Atomically swap old SKG with optimized version"""
        print("🔁 Atomic SKG swap")

        # Create backup
        await self.forge.backup_skg("pre_rebuild_backup")

        # Clear old data (mark as archived)
        await self.forge.archive_domain("orb_interactions")

        # Write optimized data
        for cluster_id, cluster in optimized_data.items():
            await self.forge.forge_skg_body(
                data={
                    "cluster_id": cluster_id,
                    "items": cluster["data"],
                    "metadata": {
                        "format": cluster["format"],
                        "rebuild_timestamp": time.time(),
                        "item_count": len(cluster["data"]),
                    },
                },
                domain=f"orb_interactions_{cluster_id}",
                priority="high" if cluster_id == "hot" else "normal",
            )

        # Update metrics
        self.metrics.fragmentation_ratio = 0.1  # Reset fragmentation

    async def _flush_emergency_cache(self):
        """Write remaining cache items and deactivate"""
        print("💨 Flushing emergency cache")

        while not self.emergency_cache.empty():
            try:
                item = self.emergency_cache.get_nowait()
                await self.forge.forge_skg_body(
                    data=item, domain="orb_interactions", priority="high"
                )
            except queue.Empty:
                break

        # Clear cache
        self.emergency_cache = queue.Queue(maxsize=1000)

    async def _rollback_rebuild(self):
        """Emergency rollback if rebuild fails"""
        print("🚨 Rolling back rebuild")

        await self.forge.restore_skg("pre_rebuild_backup")
        await self._flush_emergency_cache()

    async def get_performance_report(self) -> Dict[str, Any]:
        """Get current performance metrics and recommendations"""
        self._update_metrics()

        return {
            "health_status": "degraded" if self.metrics.is_degraded() else "healthy",
            "metrics": self.metrics.__dict__,
            "thresholds": self.thresholds,
            "rebuild_recommended": self.metrics.is_degraded()
            and (time.time() - self.last_rebuild) > self.rebuild_interval,
            "next_rebuild_allowed": self.last_rebuild + self.rebuild_interval,
            "emergency_cache_size": self.emergency_cache.qsize(),
        }
