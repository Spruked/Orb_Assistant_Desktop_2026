#!/usr/bin/env python3
"""CALI SKG v3.5 — Aggressive Learning Substrate-Mesh Integrated Intelligence.

This is the enhanced cognitive subsystem for the Orb Assistant Desktop.
Key upgrades from v3.0:
  1. MORB Deployment Bridge — spawn/evaluate MORBs via substrate mesh
  2. Substrate Mesh Traversal — walk mesh topology, discover nodes, route tasks
  3. Aggressive Learning Loop — pattern crystallization, substrate injection, vault integration
  4. Diagnostic Probe System — deep health checks with remediation suggestions
  5. Native API Registry Integration — uses the 200-entry research registry
  6. OrbSubstrateService Bridge — direct CRM/mail/service control from CALI
"""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import logging
import os
import pickle
import re
import sqlite3
import subprocess
import sys
import threading
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Set, Tuple

import numpy as np


def r_drive_path(*parts: str) -> Path:
    """Resolve R-drive substrate paths deterministically for Windows and WSL."""
    root = os.getenv("ORB_R_DRIVE_ROOT")
    if not root:
        root = "/mnt/r" if os.name != "nt" else "R:/"
    return Path(root).joinpath(*parts)


# ── Optional dependencies with graceful degradation ──────────────────────────
OPTIONAL_MODULES = {}

try:
    import aiohttp
    OPTIONAL_MODULES['aiohttp'] = aiohttp
except ImportError:
    OPTIONAL_MODULES['aiohttp'] = None

try:
    import networkx as nx
    OPTIONAL_MODULES['networkx'] = nx
except ImportError:
    OPTIONAL_MODULES['networkx'] = None

# PyTorch and ML dependencies (conditionally loaded)
ML_CONFIG = {
    'torch_enabled': os.getenv("CALI_ENABLE_TORCH", "0").strip().lower() in {"1", "true", "yes", "on"},
    'encoder_mode': os.getenv("CALI_ENCODER_MODE", "fallback").strip().lower(),
    'torch': None,
    'sentence_transformers': None
}

if ML_CONFIG['torch_enabled']:
    try:
        import torch
        ML_CONFIG['torch'] = torch
    except ImportError:
        ML_CONFIG['torch'] = None

torch = ML_CONFIG['torch']

if ML_CONFIG['encoder_mode'] not in {"", "fallback", "local_fallback", "off"}:
    try:
        from sentence_transformers import SentenceTransformer
        ML_CONFIG['sentence_transformers'] = SentenceTransformer
    except ImportError:
        ML_CONFIG['sentence_transformers'] = None
else:
    SentenceTransformer = None


logger = logging.getLogger("CALI")
if not logging.getLogger().handlers:
    logging.basicConfig(level=logging.INFO)


# ═════════════════════════════════════════════════════════════════════════════
#  FALLBACK UTILITIES
# ═════════════════════════════════════════════════════════════════════════════

class _SimpleDiGraph:
    """Fallback graph when networkx is unavailable."""

    def __init__(self) -> None:
        self._nodes: Dict[str, Dict[str, Any]] = {}
        self._edges: List[tuple[str, str, Dict[str, Any]]] = []

    def add_node(self, node_id: str, **attrs: Any) -> None:
        self._nodes[node_id] = attrs

    def add_edge(self, source: str, target: str, **attrs: Any) -> None:
        self._edges.append((source, target, attrs))

    def nodes(self) -> List[str]:
        return list(self._nodes.keys())

    def in_degree(self, node_id: str) -> int:
        return sum(1 for _, target, _ in self._edges if target == node_id)

    def number_of_nodes(self) -> int:
        return len(self._nodes)

    def number_of_edges(self) -> int:
        return len(self._edges)

    def successors(self, node_id: str) -> List[str]:
        return [target for source, target, _ in self._edges if source == node_id]

    def predecessors(self, node_id: str) -> List[str]:
        return [source for source, target, _ in self._edges if target == node_id]


class FallbackSentenceEncoder:
    """Cheap deterministic encoder when sentence-transformers is unavailable."""

    def __init__(self, dim: int = 384) -> None:
        self.dim = dim

    def encode(self, text: str) -> np.ndarray:
        vector = np.zeros(self.dim, dtype=np.float32)
        tokens = [token for token in text.lower().split() if token]
        if not tokens:
            return vector

        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dim
            vector[index] += 1.0

        norm = float(np.linalg.norm(vector))
        return vector if norm == 0 else vector / norm


# ═════════════════════════════════════════════════════════════════════════════
#  ENUMS & DATA CLASSES
# ═════════════════════════════════════════════════════════════════════════════

class ReasoningMode(Enum):
    """Four philosopher logic modes plus system logics."""

    LOCKE_EMPIRICAL = auto()
    HUME_SKEPTICAL = auto()
    KANT_SYNTHETIC = auto()
    SPINOZA_MONISTIC = auto()
    INDUCTIVE_STATISTICAL = auto()
    DEDUCTIVE_LOGICAL = auto()
    INTUITIVE_HOLISTIC = auto()


class MemoryType(Enum):
    """A priori versus a posteriori memory."""

    A_PRIORI = "a_priori"
    A_POSTERIORI = "a_posteriori"


class MORBStatus(Enum):
    """MORB execution lifecycle states."""

    PENDING = "pending"
    SPAWNING = "spawning"
    ACTIVE = "active"
    EVALUATING = "evaluating"
    PASS = "pass"
    FAIL = "fail"
    ERROR = "error"
    TIMEOUT = "timeout"


@dataclass(frozen=True)
class PhilosophicalSeed:
    """Immutable philosopher logic configuration."""

    name: str
    logic_type: ReasoningMode
    weight_formula: str
    confidence_bias: float
    description: str

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "logic_type": self.logic_type.name,
            "weight_formula": self.weight_formula,
            "confidence_bias": self.confidence_bias,
            "description": self.description,
        }


@dataclass
class LearnedPattern:
    """CALI's self-improving knowledge patterns."""

    pattern_id: str
    content: str
    reasoning_mode: ReasoningMode
    confidence: float
    truth_likelihood: float
    timestamp: datetime
    source: str
    use_count: int = 0
    last_validated: Optional[datetime] = None
    embedding: Optional[np.ndarray] = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if not self.pattern_id:
            seed = f"{self.content}{self.timestamp.isoformat()}".encode("utf-8")
            self.pattern_id = hashlib.sha256(seed).hexdigest()[:16]


@dataclass
class SwarmTask:
    """Research task for swarm orbs."""

    task_id: str
    query: str
    apis_targeted: List[Dict[str, Any]]
    priority: int
    spawn_time: datetime
    completion_callback: Optional[Callable[..., Any]] = None
    results: List[Dict[str, Any]] = field(default_factory=list)
    status: str = "pending"
    error: Optional[str] = None


@dataclass
class MORBTask:
    """MORB deployment task for substrate mesh execution."""

    morb_id: str
    task_type: str
    predicate: str
    target_node: str
    parameters: Dict[str, Any] = field(default_factory=dict)
    status: MORBStatus = MORBStatus.PENDING
    result: Optional[Dict[str, Any]] = None
    spawn_time: datetime = field(default_factory=datetime.now)
    completion_time: Optional[datetime] = None
    execution_log: List[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        if not self.morb_id:
            seed = f"{self.task_type}{self.target_node}{self.spawn_time.isoformat()}".encode("utf-8")
            self.morb_id = hashlib.sha256(seed).hexdigest()[:12]


@dataclass
class MeshNode:
    """Discovered node in the substrate mesh."""

    node_id: str
    node_type: str
    address: str
    health_status: str
    last_seen: datetime
    capabilities: List[str] = field(default_factory=list)
    load_factor: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DiagnosticReport:
    """System diagnostic finding."""

    component: str
    status: str  # "healthy", "degraded", "critical", "unknown"
    confidence: float
    findings: List[str] = field(default_factory=list)
    remediation: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.now)


# ═════════════════════════════════════════════════════════════════════════════
#  ADAPTIVE COCHLEAR PROCESSOR (Legacy)
# ═════════════════════════════════════════════════════════════════════════════

class AdaptiveCochlearProcessor:
    """Legacy auditory signal processor retained for CALI SKG fallback."""

    def __init__(self, sample_rate: int = 16000) -> None:
        self.sample_rate = sample_rate
        self.frequency_bands = 24
        self.temporal_window = 0.025
        self.attention_focus = None
        self.center_freqs = self._bark_scale(100, 8000, self.frequency_bands)

    def _bark_scale(self, f_min: float, f_max: float, n_bands: int) -> np.ndarray:
        bark_min = 13 * np.arctan(0.00076 * f_min) + 3.5 * np.arctan((f_min / 7500) ** 2)
        bark_max = 13 * np.arctan(0.00076 * f_max) + 3.5 * np.arctan((f_max / 7500) ** 2)
        barks = np.linspace(bark_min, bark_max, n_bands)
        return 7500 * np.tan(barks / 13)

    def process_audio(self, audio_signal: np.ndarray) -> Dict[str, Any]:
        normalized = np.asarray(audio_signal, dtype=np.float32).flatten()
        if normalized.size == 0:
            normalized = np.zeros(1, dtype=np.float32)

        features = {
            "spectral_envelope": self._extract_envelope(normalized).tolist(),
            "temporal_modulation": self._temporal_fine_structure(normalized).tolist(),
            "attention_salience": self._compute_salience(normalized),
            "phonetic_cues": self._extract_phonetics(normalized),
            "timestamp": datetime.now().isoformat(),
        }
        return features

    def _extract_envelope(self, signal: np.ndarray) -> np.ndarray:
        spectrum = np.fft.fft(signal)
        half = (np.arange(len(signal)) < len(signal) / 2).astype(np.float32)
        analytic = np.abs(np.fft.ifft(spectrum * half))
        decimation = max(1, int(self.sample_rate / 20))
        return analytic[::decimation][:100]

    def _temporal_fine_structure(self, signal: np.ndarray) -> np.ndarray:
        window = signal[: min(len(signal), 2048)]
        corr = np.correlate(window, window, mode="full")
        center = len(corr) // 2
        return corr[center : center + 100]

    def _compute_salience(self, signal: np.ndarray) -> float:
        energy = float(np.sum(signal ** 2))
        return float(np.clip((energy / (len(signal) + 1e-10)) * 1000, 0, 1))

    def _extract_phonetics(self, signal: np.ndarray) -> Dict[str, Any]:
        zero_crossings = int(np.sum(np.diff(np.signbit(signal)) != 0))
        return {
            "voicing_probability": float(np.clip(1 - (zero_crossings / max(len(signal), 1)), 0, 1)),
            "plosive_detected": zero_crossings > 25,
            "formant_frequencies": self.center_freqs[:4].tolist(),
        }


# ═════════════════════════════════════════════════════════════════════════════
#  SOFTMAX ADVISORY SKG
# ═════════════════════════════════════════════════════════════════════════════

class SoftMaxAdvisorySKG:
    """Confidence arbitration across multiple reasoning outputs."""

    def __init__(self) -> None:
        self.temperature = 1.0
        self.confidence_history: deque[Dict[str, Any]] = deque(maxlen=100)

    def compute_verdict(self, reasoning_outputs: List[Dict[str, Any]]) -> Dict[str, Any]:
        if not reasoning_outputs:
            return {
                "verdict": "insufficient_data",
                "confidence": 0.0,
                "truth_likelihood": 0.0,
            }

        raw_scores = np.array([item.get("raw_confidence", 0.5) for item in reasoning_outputs], dtype=np.float32)
        shifted = raw_scores - np.max(raw_scores)
        exp_scores = np.exp(shifted / max(self.temperature, 1e-6))
        weights = exp_scores / np.sum(exp_scores)

        weighted_truth = sum(item.get("truth_estimate", 0.5) * weight for item, weight in zip(reasoning_outputs, weights))
        weighted_accuracy = sum(item.get("accuracy", 0.5) * weight for item, weight in zip(reasoning_outputs, weights))

        variance = float(np.var(raw_scores))
        tension_detected = variance > 0.1
        final_confidence = min(weighted_accuracy, 0.75) if tension_detected else weighted_accuracy

        mean_score = float(np.mean(raw_scores))
        outliers = [
            item
            for item in reasoning_outputs
            if abs(item.get("raw_confidence", 0.5) - mean_score) > 0.3
        ]

        advisory = {
            "verdict": "consensus" if not outliers else "disagreement_detected",
            "confidence": float(final_confidence),
            "truth_likelihood": float(weighted_truth),
            "weights": weights.tolist(),
            "outlier_count": len(outliers),
            "tension_detected": tension_detected,
            "recommendation": "proceed" if final_confidence > 0.6 else "reevaluate",
            "timestamp": datetime.now().isoformat(),
        }
        self.confidence_history.append(advisory)
        return advisory


# ═════════════════════════════════════════════════════════════════════════════
#  BULK MIRROR CACHE
# ═════════════════════════════════════════════════════════════════════════════

class BulkMirrorCache:
    """
    Local disk mirror for API research results.
    """

    MANIFEST_PATH = r_drive_path("manifests", "research_api_manifest.json")
    BULK_MIRRORS_ROOT = r_drive_path("datasets", "bulk_mirrors")
    MAX_CACHE_AGE_HOURS = 24
    MAX_CACHE_FILE_SIZE_BYTES = 2_000_000

    def __init__(self) -> None:
        self.manifest: Dict[str, Any] = {}
        self.api_map: Dict[str, Dict[str, Any]] = {}
        self.category_map: Dict[str, str] = {}
        self._load_manifest()

    def _load_manifest(self) -> None:
        if not self.MANIFEST_PATH.exists():
            logger.warning("BulkMirrorCache: manifest not found at %s", self.MANIFEST_PATH)
            return
        try:
            self.manifest = json.loads(self.MANIFEST_PATH.read_text(encoding="utf-8"))
            for api in self.manifest.get("apis", []):
                api_id = api.get("id", "")
                if not api_id:
                    continue
                self.api_map[api_id] = api
                hint = api.get("storage_hint", "")
                if hint:
                    self.category_map[api_id] = hint
            logger.info("BulkMirrorCache: loaded %d API entries from manifest", len(self.api_map))
        except Exception as exc:
            logger.warning("BulkMirrorCache: manifest load failed: %s", exc)

    def write(self, api_id: str, data: Any, query: str = "") -> Optional[Path]:
        hint = self.category_map.get(api_id)
        if not hint:
            entry = self.api_map.get(api_id, {})
            category = entry.get("category", "misc")
            mirror_dir = self.BULK_MIRRORS_ROOT / category
        else:
            mirror_dir = Path(hint)

        try:
            mirror_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_query = "".join(c if c.isalnum() or c in "-_" else "_" for c in query[:30])
            filename = f"{api_id}_{safe_query}_{timestamp}.json" if safe_query else f"{api_id}_{timestamp}.json"
            file_path = mirror_dir / filename
            payload = json.dumps({
                "api_id": api_id,
                "query": query,
                "fetched_at": datetime.now().isoformat(),
                "data": data,
            }, ensure_ascii=False, default=str)
            if len(payload.encode("utf-8")) <= self.MAX_CACHE_FILE_SIZE_BYTES:
                file_path.write_text(payload, encoding="utf-8")
                logger.debug("BulkMirrorCache: wrote %s (%d bytes)", file_path.name, len(payload))
                return file_path
        except Exception as exc:
            logger.warning("BulkMirrorCache: write failed for %s: %s", api_id, exc)
        return None

    def read_category(self, category: str, max_files: int = 5) -> List[Dict[str, Any]]:
        mirror_dir = self.BULK_MIRRORS_ROOT / category
        if not mirror_dir.exists():
            return []

        results: List[Dict[str, Any]] = []
        cutoff = datetime.now() - timedelta(hours=self.MAX_CACHE_AGE_HOURS)

        json_files = sorted(mirror_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for json_path in json_files[:max_files]:
            try:
                mtime = datetime.fromtimestamp(json_path.stat().st_mtime)
                if mtime < cutoff:
                    continue
                payload = json.loads(json_path.read_text(encoding="utf-8"))
                results.append(payload)
            except Exception:
                continue

        return results

    def has_recent(self, category: str) -> bool:
        mirror_dir = self.BULK_MIRRORS_ROOT / category
        if not mirror_dir.exists():
            return False
        cutoff = datetime.now() - timedelta(hours=self.MAX_CACHE_AGE_HOURS)
        for p in mirror_dir.glob("*.json"):
            try:
                if datetime.fromtimestamp(p.stat().st_mtime) >= cutoff:
                    return True
            except Exception:
                continue
        return False

    def read_all_recent(self, max_per_category: int = 3) -> Dict[str, List[Dict[str, Any]]]:
        result: Dict[str, List[Dict[str, Any]]] = {}
        if not self.BULK_MIRRORS_ROOT.exists():
            return result
        for category_dir in self.BULK_MIRRORS_ROOT.iterdir():
            if not category_dir.is_dir():
                continue
            cached = self.read_category(category_dir.name, max_files=max_per_category)
            if cached:
                result[category_dir.name] = cached
        return result

    def get_prefetchable_apis(self) -> List[Dict[str, Any]]:
        return [
            api for api in self.api_map.values()
            if api.get("auth") in ("none", "optional_key", None)
        ]

    def prefetch_all(self) -> int:
        targets = self.get_prefetchable_apis()
        ok = 0
        for api in targets:
            api_id = api.get("id", "")
            category = api.get("category", "misc")
            if self.has_recent(category):
                logger.debug("BulkMirrorCache: %s already fresh, skipping", category)
                continue
            endpoints = api.get("endpoints") or {}
            first_url = next(
                (v for v in endpoints.values() if isinstance(v, str) and "{" not in v),
                None,
            )
            if not first_url:
                continue
            try:
                request = urllib.request.Request(
                    first_url,
                    headers={"User-Agent": "CALI-BulkMirror/3.5"},
                )
                with urllib.request.urlopen(request, timeout=15) as resp:
                    body = resp.read().decode("utf-8", errors="replace")
                try:
                    data = json.loads(body)
                except json.JSONDecodeError:
                    data = {"raw_text": body[:1000]}
                self.write(api_id, data, query="prefetch")
                ok += 1
                logger.info("BulkMirrorCache: pre-fetched %s → %s", api_id, category)
            except Exception as exc:
                logger.debug("BulkMirrorCache: prefetch failed %s: %s", api_id, exc)
        return ok

    def summarize_for_query(self, query: str, domains: List[str]) -> List[str]:
        tokens = set(query.lower().split())
        snippets: List[str] = []

        domain_to_category: Dict[str, str] = {
            "finance": "financial_economic",
            "financial": "financial_economic",
            "space": "space_exploration_and_mars",
            "climate": "earth_systems_and_climate",
            "weather": "earth_systems_and_climate",
            "biomedical": "biomedical_and_public_health",
            "medical": "biomedical_and_public_health",
            "geospatial": "geospatial_and_regional_analysis",
            "academic": "scientific_literature_and_evidence",
            "legal": "legal_and_regulatory",
            "economics": "macro_economic_indicators",
            "macro": "macro_economic_indicators",
            "micro": "micro_economic_markets",
            "agriculture": "agriculture_food_and_water",
            "industrial": "industrial_manufacturing",
            "machine_learning": "machine_learning",
        }

        categories_to_check: set = set()
        for domain in domains:
            slug = domain.lower().replace(" ", "_")
            mapped = domain_to_category.get(slug) or domain_to_category.get(slug.split("_")[0])
            if mapped:
                categories_to_check.add(mapped)
            else:
                candidate = self.BULK_MIRRORS_ROOT / slug
                if candidate.exists():
                    categories_to_check.add(slug)

        for category in categories_to_check:
            for cached in self.read_category(category, max_files=3):
                data = cached.get("data", {})
                text = self._extract_text(data)
                if text:
                    text_tokens = set(text.lower().split())
                    if tokens & text_tokens:
                        snippets.append(f"[{category}/{cached.get('api_id', '?')}] {text[:200]}")

        return snippets[:6]

    def weight_api_confidence(self, api_id: str, raw_quality: float) -> tuple:
        PRIORITY_BASE = {"high": 0.85, "medium": 0.70, "low": 0.55}
        AUTH_MULT = {"none": 0.90, "optional_key": 0.90, "api_key_required": 1.00}

        entry = self.api_map.get(api_id, {})
        priority = entry.get("priority", "medium")
        auth = entry.get("auth", "none")

        base = PRIORITY_BASE.get(priority, 0.70)
        mult = AUTH_MULT.get(auth, 0.90)
        raw = float(raw_quality) if 0.0 <= float(raw_quality) <= 1.0 else 0.5

        confidence = max(0.35, min(0.95, base * mult * (0.5 + raw * 0.5)))
        truth_likelihood = round(confidence * 0.90, 4)
        return round(confidence, 4), truth_likelihood

    @staticmethod
    def _extract_text(data: Any) -> str:
        if isinstance(data, str):
            return data[:400]
        if isinstance(data, dict):
            for key in ("title", "description", "name", "summary", "abstract", "text", "raw_text"):
                val = data.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()[:400]
            parts = [str(v) for v in data.values() if isinstance(v, str) and v.strip()]
            return " ".join(parts[:3])[:400]
        if isinstance(data, list) and data:
            return BulkMirrorCache._extract_text(data[0])
        return ""


# ═════════════════════════════════════════════════════════════════════════════
#  SWARM ORCHESTRATOR
# ═════════════════════════════════════════════════════════════════════════════

class CALISwarmOrchestrator:
    """Parallel API research orchestration with aggressive learning."""

    DOMAIN_ALIASES = {
        "space": ["space_earth_science_imagery", "space_astronomy_physics_additional"],
        "weather": ["weather_climate_ocean_storms"],
        "biomedical": [
            "biomedical_genomics_clinical",
            "biology_genomics_life_sciences",
            "health_medicine_public_health",
        ],
        "finance": ["economics_finance_markets"],
        "academic": [
            "knowledge_graphs_and_scholarly_metadata",
            "education_learning_research",
            "machine_learning_nlp_ai_research",
        ],
        "geospatial": [
            "geospatial_mapping_earth_data",
            "geospatial_transportation_mobility",
        ],
    }

    QUERY_PARAM_HINTS = {
        "NASA_APOD": None,
        "NASA_NeoWS": None,
        "SpaceX_Launches": None,
        "NOAA_Alerts": "query",
        "OpenWeather": "q",
        "PubMed_Search": "term",
        "ClinicalTrials": "query.term",
        "AlphaVantage": "keywords",
        "FRED": "search_text",
        "SemanticScholar": "query",
        "OpenAlex": "search",
        "OpenStreetMap": "data",
        "USGS_Earthquakes": "search",
    }

    def __init__(self, api_registry_path: Path, bulk_mirror: Optional["BulkMirrorCache"] = None) -> None:
        self.api_registry_path = api_registry_path
        self.advanced_registry_path = api_registry_path.with_name("advanced_api_imports.json")
        self.api_registry = self._load_api_registry(api_registry_path)
        self.active_tasks: Dict[str, SwarmTask] = {}
        self.task_queue: asyncio.Queue[SwarmTask] = asyncio.Queue()
        self.task_events: Dict[str, asyncio.Event] = {}
        self.session: Optional[Any] = None
        self.max_concurrent = 5
        self._workers: List[asyncio.Task[Any]] = []
        self.bulk_mirror: Optional["BulkMirrorCache"] = bulk_mirror

    def _load_api_registry(self, path: Path) -> Dict[str, List[Dict[str, Any]]]:
        merged_registry: Dict[str, List[Dict[str, Any]]] = {}

        for candidate in (path, self.advanced_registry_path):
            if not candidate.exists():
                continue

            with candidate.open("r", encoding="utf-8") as handle:
                raw_registry = json.load(handle)

            normalized = self._normalize_api_registry(raw_registry)
            for domain, entries in normalized.items():
                merged_registry.setdefault(domain, []).extend(entries)

        return merged_registry

    def _normalize_api_registry(self, raw_registry: Any) -> Dict[str, List[Dict[str, Any]]]:
        if not isinstance(raw_registry, dict):
            return {}

        if "domains" in raw_registry and isinstance(raw_registry["domains"], list):
            normalized: Dict[str, List[Dict[str, Any]]] = {}
            for domain_block in raw_registry["domains"]:
                domain_key = self._slugify(domain_block.get("domain") or domain_block.get("category") or "misc")
                entries = [
                    self._normalize_api_entry(item, domain_key)
                    for item in domain_block.get("entries", [])
                    if isinstance(item, dict)
                ]
                if entries:
                    normalized[domain_key] = entries
            return normalized

        if "entries" in raw_registry and isinstance(raw_registry["entries"], list):
            normalized: Dict[str, List[Dict[str, Any]]] = {}
            for item in raw_registry["entries"]:
                if not isinstance(item, dict):
                    continue
                domain_key = self._slugify(item.get("domain") or item.get("category") or "misc")
                normalized.setdefault(domain_key, []).append(self._normalize_api_entry(item, domain_key))
            return normalized

        if "apis" in raw_registry and isinstance(raw_registry["apis"], list):
            normalized: Dict[str, List[Dict[str, Any]]] = {}
            for item in raw_registry["apis"]:
                if not isinstance(item, dict):
                    continue
                domain_key = self._slugify(item.get("category") or raw_registry.get("category") or "advanced_api_imports")
                normalized.setdefault(domain_key, []).append(self._normalize_api_entry(item, domain_key))
            return normalized

        normalized: Dict[str, List[Dict[str, Any]]] = {}
        for domain_key, entries in raw_registry.items():
            if not isinstance(entries, list):
                continue
            slug = self._slugify(domain_key)
            normalized[slug] = [
                self._normalize_api_entry(item, slug)
                for item in entries
                if isinstance(item, dict)
            ]
        return normalized

    def _normalize_api_entry(self, api_entry: Dict[str, Any], fallback_domain: str) -> Dict[str, Any]:
        normalized = dict(api_entry)
        endpoint = normalized.get("endpoint") or normalized.get("reference_url")

        if not endpoint and isinstance(normalized.get("endpoints"), dict):
            endpoint = next(
                (
                    value
                    for value in normalized["endpoints"].values()
                    if isinstance(value, str) and value
                ),
                "",
            )

        normalized["endpoint"] = endpoint or ""
        normalized["domain"] = self._slugify(normalized.get("domain") or normalized.get("category") or fallback_domain)
        normalized["name"] = normalized.get("name") or normalized.get("provider") or "unknown"
        return normalized

    def _resolve_domain_keys(self, requested_domains: List[str]) -> List[str]:
        resolved: List[str] = []
        available = list(self.api_registry.keys())

        for domain in requested_domains:
            slug = self._slugify(domain)
            if slug in self.DOMAIN_ALIASES:
                resolved.extend(self.DOMAIN_ALIASES[slug])
                continue
            if slug in self.api_registry:
                resolved.append(slug)
                continue

            fuzzy_matches = [candidate for candidate in available if slug in candidate or candidate in slug]
            resolved.extend(fuzzy_matches[:3])

        if not resolved:
            return []

        ordered: List[str] = []
        for domain in resolved:
            if domain not in ordered:
                ordered.append(domain)
        return ordered

    @staticmethod
    def _slugify(value: str) -> str:
        lowered = str(value or "").strip().lower()
        cleaned = []
        previous_underscore = False
        for char in lowered:
            if char.isalnum():
                cleaned.append(char)
                previous_underscore = False
            elif not previous_underscore:
                cleaned.append("_")
                previous_underscore = True

        return "".join(cleaned).strip("_") or "misc"

    async def initialize(self) -> None:
        if self.session is None and aiohttp is not None:
            self.session = aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=30),
                headers={"User-Agent": "CALI-Orb-Research/3.5"},
            )

        if not self._workers:
            self._workers = [
                asyncio.create_task(self._swarm_worker(index), name=f"cali-swarm-{index}")
                for index in range(self.max_concurrent)
            ]

    async def _swarm_worker(self, index: int) -> None:
        while True:
            task = await self.task_queue.get()
            try:
                await self._execute_swarm_task(task)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                task.status = "failed"
                task.error = str(exc)
                logger.warning("Swarm worker %s failed task %s: %s", index, task.task_id, exc)
            finally:
                event = self.task_events.get(task.task_id)
                if event:
                    event.set()
                self.task_queue.task_done()

    async def spawn_research_orbs(self, query: str, domains: List[str]) -> str:
        task_id = hashlib.sha256(f"{query}{datetime.now().isoformat()}".encode("utf-8")).hexdigest()[:12]
        targeted_apis: List[Dict[str, Any]] = []
        resolved_domains = self._resolve_domain_keys(domains) or domains
        for domain in resolved_domains:
            targeted_apis.extend(self.api_registry.get(domain, []))

        if not targeted_apis:
            for entries in self.api_registry.values():
                targeted_apis.extend(entries[:1])

        task = SwarmTask(
            task_id=task_id,
            query=query,
            apis_targeted=targeted_apis[:10],
            priority=5,
            spawn_time=datetime.now(),
        )
        self.active_tasks[task_id] = task
        self.task_events[task_id] = asyncio.Event()
        await self.task_queue.put(task)
        logger.info("Spawned research orbs for task %s: %s APIs", task_id, len(task.apis_targeted))
        return task_id

    async def _execute_swarm_task(self, task: SwarmTask) -> None:
        task.status = "active"

        async def fetch_api(api_config: Dict[str, Any]) -> Dict[str, Any]:
            try:
                url, params = self._build_request(api_config, task.query)
                data = await self._request_data(url, params=params, headers=api_config.get("headers"))
                return {
                    "api": api_config.get("name", "unknown"),
                    "domain": api_config.get("domain", "unknown"),
                    "data": data,
                    "timestamp": datetime.now().isoformat(),
                    "confidence": self._assess_data_quality(data),
                }
            except Exception as exc:
                return {
                    "api": api_config.get("name", "unknown"),
                    "domain": api_config.get("domain", "unknown"),
                    "error": str(exc),
                    "timestamp": datetime.now().isoformat(),
                }

        results = await asyncio.gather(*(fetch_api(api) for api in task.apis_targeted))
        task.results = [result for result in results if result]
        task.status = "complete"

        if self.bulk_mirror:
            for result in task.results:
                if result.get("error"):
                    continue
                api_name = result.get("api", "")
                api_id = next(
                    (aid for aid, entry in self.bulk_mirror.api_map.items()
                     if entry.get("name", "") == api_name or aid == api_name),
                    api_name.lower().replace(" ", "_"),
                )
                raw_quality = result.get("confidence", 0.5)
                weighted_conf, truth_lk = self.bulk_mirror.weight_api_confidence(api_id, raw_quality)
                result["api_id"] = api_id
                result["weighted_confidence"] = weighted_conf
                result["truth_likelihood"] = truth_lk
                self.bulk_mirror.write(api_id, result.get("data"), query=task.query)

        if task.completion_callback:
            task.completion_callback(task)
        logger.info("Swarm task %s complete: %s results", task.task_id, len(task.results))

    def _build_request(self, api_config: Dict[str, Any], query: str) -> tuple[str, Dict[str, Any]]:
        endpoint = api_config.get("endpoint", "")
        if "{query}" in endpoint:
            endpoint = endpoint.format(query=urllib.parse.quote(query))

        params = dict(api_config.get("params", {}))
        rendered_params: Dict[str, Any] = {}
        for key, value in params.items():
            if isinstance(value, str):
                rendered_params[key] = value.format(query=query)
            else:
                rendered_params[key] = value

        hint = self.QUERY_PARAM_HINTS.get(api_config.get("name"))
        if query and hint and hint not in rendered_params:
            rendered_params[hint] = query

        api_key_env = api_config.get("api_key_env")
        api_key_param = api_config.get("api_key_param")
        if api_key_env and api_key_param:
            api_key = os.getenv(api_key_env)
            if api_key:
                rendered_params[api_key_param] = api_key

        if api_config.get("name") == "OpenStreetMap" and "data" in rendered_params:
            rendered_params["data"] = rendered_params["data"].format(query=query)

        return endpoint, rendered_params

    async def _request_data(
        self,
        url: str,
        params: Optional[Dict[str, Any]] = None,
        headers: Optional[Dict[str, str]] = None,
    ) -> Any:
        if self.session is not None:
            async with self.session.get(url, params=params or {}, headers=headers) as response:
                text = await response.text()
                return self._decode_response(text, response.headers.get("Content-Type", ""))

        return await asyncio.to_thread(self._urllib_fetch, url, params or {}, headers or {})

    def _urllib_fetch(self, url: str, params: Dict[str, Any], headers: Dict[str, str]) -> Any:
        query_string = urllib.parse.urlencode(params, doseq=True)
        full_url = f"{url}?{query_string}" if query_string else url
        request = urllib.request.Request(full_url, headers=headers or {"User-Agent": "CALI-Orb-Research/3.5"})
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8", errors="replace")
            content_type = response.headers.get("Content-Type", "")
        return self._decode_response(body, content_type)

    def _decode_response(self, payload: str, content_type: str) -> Any:
        if "json" in content_type.lower():
            try:
                return json.loads(payload)
            except json.JSONDecodeError:
                return {"raw_text": payload[:2000]}

        try:
            return json.loads(payload)
        except json.JSONDecodeError:
            pass

        try:
            root = ET.fromstring(payload)
            return self._xml_to_dict(root)
        except ET.ParseError:
            return {"raw_text": payload[:2000]}

    def _xml_to_dict(self, node: ET.Element) -> Any:
        children = list(node)
        if not children:
            return node.text or ""

        result: Dict[str, Any] = {}
        for child in children:
            value = self._xml_to_dict(child)
            if child.tag in result:
                existing = result[child.tag]
                if not isinstance(existing, list):
                    result[child.tag] = [existing]
                result[child.tag].append(value)
            else:
                result[child.tag] = value
        return result

    def _assess_data_quality(self, data: Any) -> float:
        if not data:
            return 0.0
        if isinstance(data, dict):
            total = max(len(data), 1)
            present = len([value for value in data.values() if value not in (None, "", [], {})])
            return min(1.0, present / total)
        if isinstance(data, list):
            return min(1.0, len(data) / 10.0)
        return 0.5

    async def ingest_results(self, task_id: str) -> Dict[str, Any]:
        task = self.active_tasks.get(task_id)
        if task is None:
            return {"error": "Task not found"}

        event = self.task_events.get(task_id)
        if event is not None:
            await event.wait()

        return {
            "task_id": task_id,
            "sources_queried": len(task.apis_targeted),
            "successful_returns": len([result for result in task.results if "data" in result]),
            "key_findings": self._extract_findings(task.results),
            "confidence_aggregate": float(
                np.mean([result.get("confidence", 0.5) for result in task.results if "confidence" in result])
            )
            if task.results
            else 0.0,
            "ingestion_timestamp": datetime.now().isoformat(),
            "ready_for_voice": True,
            "status": task.status,
            "error": task.error,
        }

    def _extract_findings(self, results: List[Dict[str, Any]]) -> List[str]:
        findings: List[str] = []
        for result in results:
            data = result.get("data")
            if not data:
                continue

            source = result.get("api", "unknown source")
            summary = self._summarize_payload(data)
            if summary:
                findings.append(f"From {source}: {summary}")

        return findings[:5]

    def _summarize_payload(self, data: Any) -> Optional[str]:
        if isinstance(data, dict):
            for key in ("title", "name", "headline", "message", "description"):
                value = data.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()[:180]

            for key in ("results", "data", "items", "studies"):
                nested = data.get(key)
                if isinstance(nested, list) and nested:
                    return f"{len(nested)} records found"

            return f"{len(data)} fields returned"

        if isinstance(data, list):
            return f"{len(data)} records found"

        if isinstance(data, str) and data.strip():
            return data.strip()[:180]

        return None

    async def close(self) -> None:
        for worker in self._workers:
            worker.cancel()

        if self._workers:
            await asyncio.gather(*self._workers, return_exceptions=True)
        self._workers = []

        if self.session is not None:
            await self.session.close()
            self.session = None


# ═════════════════════════════════════════════════════════════════════════════
#  MORB DEPLOYMENT BRIDGE
# ═════════════════════════════════════════════════════════════════════════════

class MORBDeploymentBridge:
    """
    Bridge between CALI and the MORB (Mini-Orb Reasoning Bot) deployment system.

    MORBs are deterministic evaluators — they run predicate logic, decide PASS/FAIL,
    and return results. They do NOT reason about meaning, store memory, or maintain persona.
    All of that belongs to CALI (the Prime Orb).

    This bridge:
      1. Receives MORB deployment requests from CALI
      2. Routes them to the substrate mesh for execution
      3. Collects PASS/FAIL results
      4. Returns structured verdicts to CALI's SoftMax advisory
    """

    def __init__(self, mesh_root: Path, cali_instance: "CALISKG") -> None:
        self.mesh_root = Path(mesh_root)
        self.cali = cali_instance
        self.active_morbs: Dict[str, MORBTask] = {}
        self.morb_history: deque[MORBTask] = deque(maxlen=500)
        self.deployment_log: Path = self.mesh_root / "logs" / "morb_deployments.jsonl"
        self.deployment_log.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def deploy_morb(
        self,
        task_type: str,
        predicate: str,
        target_node: str,
        parameters: Optional[Dict[str, Any]] = None,
        timeout_seconds: int = 30,
    ) -> Dict[str, Any]:
        """
        Deploy a MORB to evaluate a predicate on a target mesh node.

        task_type: "health_check", "integrity_scan", "data_validation", "compliance_audit"
        predicate: The deterministic logic string the MORB evaluates
        target_node: The mesh node ID to evaluate against
        """
        morb_task = MORBTask(
            task_type=task_type,
            predicate=predicate,
            target_node=target_node,
            parameters=parameters or {},
        )

        with self._lock:
            self.active_morbs[morb_task.morb_id] = morb_task

        # Write deployment artifact to mesh
        artifact = self._build_artifact(morb_task)
        self._write_mesh_artifact(artifact)

        # Execute the MORB evaluation (deterministic, no reasoning)
        result = self._execute_morb_evaluation(morb_task, timeout_seconds)

        morb_task.result = result
        morb_task.status = MORBStatus(result.get("status", "error"))
        morb_task.completion_time = datetime.now()

        with self._lock:
            self.morb_history.append(morb_task)
            if morb_task.morb_id in self.active_morbs:
                del self.active_morbs[morb_task.morb_id]

        self._log_deployment(morb_task)

        return {
            "morb_id": morb_task.morb_id,
            "status": morb_task.status.value,
            "task_type": task_type,
            "target_node": target_node,
            "predicate": predicate,
            "result": result,
            "execution_log": morb_task.execution_log,
            "latency_ms": result.get("latency_ms", 0),
        }

    def deploy_morb_swarm(
        self,
        task_type: str,
        predicate: str,
        target_nodes: List[str],
        parameters: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Deploy MORBs across multiple nodes in parallel."""
        results: List[Dict[str, Any]] = []
        pass_count = 0
        fail_count = 0
        error_count = 0

        for node in target_nodes:
            result = self.deploy_morb(task_type, predicate, node, parameters)
            results.append(result)
            status = result.get("status", "error")
            if status == "pass":
                pass_count += 1
            elif status == "fail":
                fail_count += 1
            else:
                error_count += 1

        total = len(target_nodes)
        consensus = "pass" if pass_count > total / 2 else "fail" if fail_count > total / 2 else "inconclusive"

        return {
            "swarm_id": hashlib.sha256(f"{task_type}{predicate}{datetime.now().isoformat()}".encode()).hexdigest()[:12],
            "task_type": task_type,
            "predicate": predicate,
            "nodes_evaluated": total,
            "pass_count": pass_count,
            "fail_count": fail_count,
            "error_count": error_count,
            "consensus": consensus,
            "confidence": max(pass_count, fail_count) / total if total > 0 else 0.0,
            "individual_results": results,
        }

    def _build_artifact(self, morb_task: MORBTask) -> Dict[str, Any]:
        return {
            "artifact_id": morb_task.morb_id,
            "artifact_type": "task",
            "source_orb": self.cali.instance_id,
            "target_orb": morb_task.target_node,
            "created_at": morb_task.spawn_time.isoformat(),
            "priority": "high",
            "content_hash": hashlib.sha256(morb_task.predicate.encode()).hexdigest()[:16],
            "tags": ["morb", morb_task.task_type, "deterministic"],
            "payload": {
                "task_type": morb_task.task_type,
                "predicate": morb_task.predicate,
                "parameters": morb_task.parameters,
            },
        }

    def _write_mesh_artifact(self, artifact: Dict[str, Any]) -> None:
        try:
            tasks_dir = self.mesh_root / "tasks" / "broadcast"
            tasks_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = tasks_dir / f"{artifact['artifact_id']}.json"
            artifact_path.write_text(json.dumps(artifact, indent=2), encoding="utf-8")
        except Exception as exc:
            logger.warning("MORB artifact write failed: %s", exc)

    def _execute_morb_evaluation(self, morb_task: MORBTask, timeout: int) -> Dict[str, Any]:
        """
        Execute deterministic predicate evaluation.
        MORBs do NOT reason — they evaluate pre-defined logic against data.
        """
        start_time = time.time()
        morb_task.execution_log.append(f"[{datetime.now().isoformat()}] MORB {morb_task.morb_id} spawned")
        morb_task.execution_log.append(f"  Task: {morb_task.task_type}")
        morb_task.execution_log.append(f"  Target: {morb_task.target_node}")
        morb_task.execution_log.append(f"  Predicate: {morb_task.predicate}")

        try:
            # Phase 1: Resolve target node
            node_data = self._resolve_node_data(morb_task.target_node)
            if node_data is None:
                return {
                    "status": "error",
                    "verdict": "NODE_UNRESOLVED",
                    "detail": f"Target node {morb_task.target_node} not found in mesh",
                    "latency_ms": int((time.time() - start_time) * 1000),
                }

            morb_task.execution_log.append(f"  Node resolved: {node_data.get('node_type', 'unknown')}")

            # Phase 2: Evaluate predicate against node data
            evaluation = self._evaluate_predicate(morb_task.predicate, node_data, morb_task.parameters)
            morb_task.execution_log.append(f"  Evaluation result: {evaluation}")

            # Phase 3: Deterministic PASS/FAIL
            if evaluation.get("satisfied", False):
                verdict = "PASS"
                status = "pass"
            else:
                verdict = "FAIL"
                status = "fail"

            latency_ms = int((time.time() - start_time) * 1000)

            return {
                "status": status,
                "verdict": verdict,
                "evaluation": evaluation,
                "node_type": node_data.get("node_type"),
                "node_health": node_data.get("health_status"),
                "latency_ms": latency_ms,
            }

        except Exception as exc:
            morb_task.execution_log.append(f"  ERROR: {exc}")
            return {
                "status": "error",
                "verdict": "EXECUTION_ERROR",
                "detail": str(exc),
                "latency_ms": int((time.time() - start_time) * 1000),
            }

    def _resolve_node_data(self, node_id: str) -> Optional[Dict[str, Any]]:
        """Resolve a mesh node by ID from the substrate registry."""
        try:
            registry_path = self.mesh_root / "manifests" / "orb_registry.json"
            if registry_path.exists():
                registry = json.loads(registry_path.read_text(encoding="utf-8"))
                nodes = registry.get("nodes", [])
                for node in nodes:
                    if node.get("node_id") == node_id:
                        return node
            # Fallback: check mesh protocol nodes
            protocol_path = self.mesh_root / "manifests" / "mesh_protocol.json"
            if protocol_path.exists():
                protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
                nodes = protocol.get("nodes", [])
                for node in nodes:
                    if node.get("node_id") == node_id:
                        return node
        except Exception as exc:
            logger.warning("Node resolution failed for %s: %s", node_id, exc)
        return None

    def _evaluate_predicate(self, predicate: str, node_data: Dict[str, Any], parameters: Dict[str, Any]) -> Dict[str, Any]:
        """
        Evaluate a predicate string against node data.
        Supports: EXISTS, EQUALS, GREATER_THAN, LESS_THAN, CONTAINS, REGEX_MATCH
        """
        predicate = predicate.strip().upper()
        result = {"satisfied": False, "checks": []}

        # Parse simple predicate format: "OPERATOR field value"
        parts = predicate.split(None, 2)
        if len(parts) < 2:
            result["checks"].append({"error": "Invalid predicate format"})
            return result

        operator = parts[0]
        field = parts[1] if len(parts) > 1 else ""
        value = parts[2] if len(parts) > 2 else ""

        node_value = node_data.get(field)

        if operator == "EXISTS":
            satisfied = node_value is not None and node_value != ""
            result["checks"].append({"field": field, "exists": satisfied})
            result["satisfied"] = satisfied

        elif operator == "EQUALS":
            satisfied = str(node_value) == value
            result["checks"].append({"field": field, "expected": value, "actual": str(node_value), "match": satisfied})
            result["satisfied"] = satisfied

        elif operator == "GREATER_THAN":
            try:
                satisfied = float(node_value or 0) > float(value)
            except (ValueError, TypeError):
                satisfied = False
            result["checks"].append({"field": field, "expected_gt": value, "actual": node_value, "satisfied": satisfied})
            result["satisfied"] = satisfied

        elif operator == "LESS_THAN":
            try:
                satisfied = float(node_value or 0) < float(value)
            except (ValueError, TypeError):
                satisfied = False
            result["checks"].append({"field": field, "expected_lt": value, "actual": node_value, "satisfied": satisfied})
            result["satisfied"] = satisfied

        elif operator == "CONTAINS":
            satisfied = value.lower() in str(node_value or "").lower()
            result["checks"].append({"field": field, "search": value, "found": satisfied})
            result["satisfied"] = satisfied

        elif operator == "REGEX_MATCH":
            try:
                pattern = re.compile(value, re.IGNORECASE)
                satisfied = bool(pattern.search(str(node_value or "")))
            except re.error:
                satisfied = False
            result["checks"].append({"field": field, "pattern": value, "match": satisfied})
            result["satisfied"] = satisfied

        else:
            result["checks"].append({"error": f"Unknown operator: {operator}"})

        return result

    def _log_deployment(self, morb_task: MORBTask) -> None:
        try:
            log_entry = {
                "morb_id": morb_task.morb_id,
                "task_type": morb_task.task_type,
                "target_node": morb_task.target_node,
                "status": morb_task.status.value,
                "spawn_time": morb_task.spawn_time.isoformat(),
                "completion_time": morb_task.completion_time.isoformat() if morb_task.completion_time else None,
                "result_summary": morb_task.result.get("verdict") if morb_task.result else None,
            }
            with self.deployment_log.open("a", encoding="utf-8") as f:
                f.write(json.dumps(log_entry) + "\n")
        except Exception as exc:
            logger.warning("MORB deployment log write failed: %s", exc)

    def get_morb_status(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "active_count": len(self.active_morbs),
                "history_count": len(self.morb_history),
                "active": [{"morb_id": m.morb_id, "task_type": m.task_type, "target": m.target_node} for m in self.active_morbs.values()],
                "recent_history": [{"morb_id": m.morb_id, "status": m.status.value, "target": m.target_node} for m in list(self.morb_history)[-10:]],
            }


# ═════════════════════════════════════════════════════════════════════════════
#  SUBSTRATE MESH TRAVERSER
# ═════════════════════════════════════════════════════════════════════════════

class SubstrateMeshTraverser:
    """
    Walks the substrate mesh topology, discovers nodes, probes health,
    and routes tasks between ORB instances.
    """

    def __init__(self, mesh_root: Path, cali_instance: "CALISKG") -> None:
        self.mesh_root = Path(mesh_root)
        self.cali = cali_instance
        self.discovered_nodes: Dict[str, MeshNode] = {}
        self.mesh_graph = nx.DiGraph() if nx is not None else _SimpleDiGraph()
        self.traversal_log: deque[Dict[str, Any]] = deque(maxlen=200)
        self._lock = threading.Lock()
        self._last_full_scan: Optional[datetime] = None

    def discover_nodes(self, force_rescan: bool = False) -> List[MeshNode]:
        """Discover all nodes in the substrate mesh."""
        if not force_rescan and self._last_full_scan:
            age = datetime.now() - self._last_full_scan
            if age < timedelta(minutes=5):
                return list(self.discovered_nodes.values())

        nodes: List[MeshNode] = []

        # Scan 1: orb_registry.json
        try:
            registry_path = self.mesh_root / "manifests" / "orb_registry.json"
            if registry_path.exists():
                registry = json.loads(registry_path.read_text(encoding="utf-8"))
                for node_data in registry.get("nodes", []):
                    node = self._parse_node(node_data)
                    if node:
                        nodes.append(node)
        except Exception as exc:
            logger.warning("Mesh registry scan failed: %s", exc)

        # Scan 2: mesh_protocol.json
        try:
            protocol_path = self.mesh_root / "manifests" / "mesh_protocol.json"
            if protocol_path.exists():
                protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
                for node_data in protocol.get("nodes", []):
                    node = self._parse_node(node_data)
                    if node and node.node_id not in {n.node_id for n in nodes}:
                        nodes.append(node)
        except Exception as exc:
            logger.warning("Mesh protocol scan failed: %s", exc)

        # Scan 3: service_registry.json
        try:
            service_path = self.mesh_root / "manifests" / "service_registry.json"
            if service_path.exists():
                services = json.loads(service_path.read_text(encoding="utf-8"))
                for svc_id, svc_data in services.get("services", {}).items():
                    node = MeshNode(
                        node_id=f"svc_{svc_id}",
                        node_type="service",
                        address=str(svc_data.get("api_base", "")),
                        health_status="unknown",
                        last_seen=datetime.now(),
                        capabilities=[svc_data.get("type", "unknown")],
                        metadata=svc_data,
                    )
                    if node.node_id not in {n.node_id for n in nodes}:
                        nodes.append(node)
        except Exception as exc:
            logger.warning("Service registry scan failed: %s", exc)

        # Scan 4: Live heartbeat snapshots
        try:
            snapshots_dir = self.mesh_root / "exports"
            if snapshots_dir.exists():
                for instance_dir in snapshots_dir.iterdir():
                    if not instance_dir.is_dir():
                        continue
                    heartbeat_path = instance_dir / "state_snapshots" / "heartbeat.json"
                    if heartbeat_path.exists():
                        try:
                            hb = json.loads(heartbeat_path.read_text(encoding="utf-8"))
                            node = MeshNode(
                                node_id=hb.get("instance_id", instance_dir.name),
                                node_type="orb_instance",
                                address=str(instance_dir),
                                health_status="active" if hb.get("running") else "inactive",
                                last_seen=datetime.fromtimestamp(hb.get("ts", 0)),
                                capabilities=["cognition", "voice", "research"] if hb.get("listening_enabled") else ["cognition"],
                                load_factor=hb.get("hlsf", {}).get("field_density", 0) / 100.0,
                                metadata=hb,
                            )
                            if node.node_id not in {n.node_id for n in nodes}:
                                nodes.append(node)
                        except Exception:
                            continue
        except Exception as exc:
            logger.warning("Heartbeat scan failed: %s", exc)

        with self._lock:
            self.discovered_nodes = {n.node_id: n for n in nodes}
            self._rebuild_graph()
            self._last_full_scan = datetime.now()

        self.traversal_log.append({
            "event": "full_scan",
            "timestamp": datetime.now().isoformat(),
            "nodes_found": len(nodes),
            "node_types": list(set(n.node_type for n in nodes)),
        })

        return nodes

    def _parse_node(self, node_data: Dict[str, Any]) -> Optional[MeshNode]:
        node_id = node_data.get("node_id") or node_data.get("id") or node_data.get("instance_id")
        if not node_id:
            return None
        return MeshNode(
            node_id=str(node_id),
            node_type=node_data.get("node_type", "unknown"),
            address=node_data.get("address") or node_data.get("api_base") or "",
            health_status=node_data.get("health_status", "unknown"),
            last_seen=datetime.fromisoformat(node_data["last_seen"]) if "last_seen" in node_data else datetime.now(),
            capabilities=node_data.get("capabilities", []),
            load_factor=float(node_data.get("load_factor", 0)),
            metadata=node_data,
        )

    def _rebuild_graph(self) -> None:
        self.mesh_graph = nx.DiGraph() if nx is not None else _SimpleDiGraph()
        for node in self.discovered_nodes.values():
            self.mesh_graph.add_node(
                node.node_id,
                node_type=node.node_type,
                health=node.health_status,
                load=node.load_factor,
            )
        # Add edges based on known relationships
        for node_id, node in self.discovered_nodes.items():
            metadata = node.metadata
            if "parent_node" in metadata:
                self.mesh_graph.add_edge(metadata["parent_node"], node_id, relation="parent")
            if "peers" in metadata:
                for peer in metadata["peers"]:
                    self.mesh_graph.add_edge(node_id, peer, relation="peer")
            if "services" in metadata:
                for svc in metadata["services"]:
                    self.mesh_graph.add_edge(node_id, f"svc_{svc}", relation="hosts")

    def probe_node_health(self, node_id: str) -> Dict[str, Any]:
        """Deep health probe of a specific mesh node."""
        node = self.discovered_nodes.get(node_id)
        if not node:
            return {"error": "Node not found", "node_id": node_id}

        findings = []
        remediation = []

        # Check heartbeat freshness
        age = datetime.now() - node.last_seen
        if age > timedelta(minutes=10):
            findings.append(f"Heartbeat stale: {age.total_seconds()/60:.1f} minutes old")
            remediation.append("Restart node or check network connectivity")
        elif age > timedelta(minutes=2):
            findings.append(f"Heartbeat lagging: {age.total_seconds():.0f} seconds")
            remediation.append("Monitor for degradation")

        # Check load factor
        if node.load_factor > 0.8:
            findings.append(f"High load: {node.load_factor:.2f}")
            remediation.append("Consider load balancing or scaling")
        elif node.load_factor > 0.5:
            findings.append(f"Elevated load: {node.load_factor:.2f}")

        # Check health status
        if node.health_status == "critical":
            findings.append("Node reports critical health")
            remediation.append("Immediate intervention required")
        elif node.health_status == "degraded":
            findings.append("Node reports degraded health")
            remediation.append("Investigate logs and metrics")

        # Probe address if HTTP
        if node.address.startswith("http"):
            try:
                req = urllib.request.Request(node.address, method="HEAD")
                with urllib.request.urlopen(req, timeout=5) as resp:
                    if resp.status >= 500:
                        findings.append(f"HTTP {resp.status} from {node.address}")
                        remediation.append("Check service logs for errors")
            except Exception as exc:
                findings.append(f"Unreachable: {exc}")
                remediation.append("Verify service is running and port is accessible")

        status = "healthy"
        if any("critical" in f.lower() for f in findings):
            status = "critical"
        elif any("degraded" in f.lower() or "unreachable" in f.lower() for f in findings):
            status = "degraded"
        elif findings:
            status = "warning"

        report = DiagnosticReport(
            component=f"mesh_node:{node_id}",
            status=status,
            confidence=0.9 if status == "healthy" else 0.7,
            findings=findings,
            remediation=remediation,
        )

        return {
            "node_id": node_id,
            "status": status,
            "confidence": report.confidence,
            "findings": findings,
            "remediation": remediation,
            "node_type": node.node_type,
            "last_seen": node.last_seen.isoformat(),
            "load_factor": node.load_factor,
        }

    def find_path(self, source: str, target: str) -> Optional[List[str]]:
        """Find a path between two nodes in the mesh."""
        if nx is not None:
            try:
                return nx.shortest_path(self.mesh_graph, source, target)
            except (nx.NetworkXNoPath, nx.NodeNotFound):
                return None
        else:
            # BFS fallback
            visited = {source}
            queue = deque([(source, [source])])
            while queue:
                current, path = queue.popleft()
                if current == target:
                    return path
                for succ in self.mesh_graph.successors(current):
                    if succ not in visited:
                        visited.add(succ)
                        queue.append((succ, path + [succ]))
            return None

    def route_task(self, task_payload: Dict[str, Any], target_node: str) -> Dict[str, Any]:
        """Route a task to a specific mesh node."""
        source = self.cali.instance_id
        path = self.find_path(source, target_node)

        if not path:
            return {
                "routed": False,
                "error": "No path to target node",
                "source": source,
                "target": target_node,
            }

        # Write task artifact to mesh
        try:
            task_dir = self.mesh_root / "tasks" / f"{source}_to_{target_node}"
            task_dir.mkdir(parents=True, exist_ok=True)
            task_id = hashlib.sha256(f"{source}{target_node}{datetime.now().isoformat()}".encode()).hexdigest()[:12]
            artifact = {
                "artifact_id": task_id,
                "artifact_type": "task",
                "source_orb": source,
                "target_orb": target_node,
                "created_at": datetime.now().isoformat(),
                "priority": task_payload.get("priority", "normal"),
                "content_hash": hashlib.sha256(json.dumps(task_payload).encode()).hexdigest()[:16],
                "tags": task_payload.get("tags", []),
                "payload": task_payload,
            }
            (task_dir / f"{task_id}.json").write_text(json.dumps(artifact, indent=2), encoding="utf-8")

            return {
                "routed": True,
                "task_id": task_id,
                "path": path,
                "hops": len(path) - 1,
                "artifact_path": str(task_dir / f"{task_id}.json"),
            }
        except Exception as exc:
            return {
                "routed": False,
                "error": str(exc),
                "source": source,
                "target": target_node,
            }

    def get_mesh_topology(self) -> Dict[str, Any]:
        """Return current mesh topology snapshot."""
        return {
            "node_count": self.mesh_graph.number_of_nodes(),
            "edge_count": self.mesh_graph.number_of_edges(),
            "nodes": [
                {
                    "id": nid,
                    "type": data.get("node_type", "unknown"),
                    "health": data.get("health", "unknown"),
                    "load": data.get("load", 0),
                }
                for nid, data in (self.mesh_graph._nodes.items() if hasattr(self.mesh_graph, '_nodes') else [(n, {}) for n in self.mesh_graph.nodes()])
            ],
            "last_scan": self._last_full_scan.isoformat() if self._last_full_scan else None,
        }


# ═════════════════════════════════════════════════════════════════════════════
#  DIAGNOSTIC PROBE SYSTEM
# ═════════════════════════════════════════════════════════════════════════════

class DiagnosticProbeSystem:
    """
    Deep system diagnostics with automated remediation suggestions.
    Probes all known subsystems and produces actionable reports.
    """

    def __init__(self, cali_instance: "CALISKG") -> None:
        self.cali = cali_instance
        self.reports: deque[DiagnosticReport] = deque(maxlen=100)
        self.probe_history: List[Dict[str, Any]] = []
        self._lock = threading.Lock()

    def full_system_probe(self) -> Dict[str, Any]:
        """Run comprehensive diagnostics across all subsystems."""
        reports: List[DiagnosticReport] = []

        # 1. Mesh health
        reports.append(self._probe_mesh_health())

        # 2. API registry health
        reports.append(self._probe_api_registry())

        # 3. Bulk mirror health
        reports.append(self._probe_bulk_mirror())

        # 4. Knowledge graph health
        reports.append(self._probe_knowledge_graph())

        # 5. Pattern database health
        reports.append(self._probe_patterns_db())

        # 6. Vault health
        reports.append(self._probe_vaults())

        # 7. Encoder health
        reports.append(self._probe_encoder())

        # 8. MORB deployment health
        reports.append(self._probe_morb_system())

        # 9. Substrate service health
        reports.append(self._probe_substrate_services())

        # Aggregate
        critical = sum(1 for r in reports if r.status == "critical")
        degraded = sum(1 for r in reports if r.status == "degraded")
        warning = sum(1 for r in reports if r.status == "warning")
        healthy = sum(1 for r in reports if r.status == "healthy")

        overall_status = "healthy"
        if critical > 0:
            overall_status = "critical"
        elif degraded > 0:
            overall_status = "degraded"
        elif warning > 0:
            overall_status = "warning"

        with self._lock:
            self.reports.extend(reports)
            self.probe_history.append({
                "timestamp": datetime.now().isoformat(),
                "overall_status": overall_status,
                "component_count": len(reports),
                "breakdown": {"critical": critical, "degraded": degraded, "warning": warning, "healthy": healthy},
            })

        return {
            "overall_status": overall_status,
            "timestamp": datetime.now().isoformat(),
            "components": [self._report_to_dict(r) for r in reports],
            "summary": {
                "critical": critical,
                "degraded": degraded,
                "warning": warning,
                "healthy": healthy,
            },
            "top_remediations": self._collect_remediations(reports),
        }

    def _probe_mesh_health(self) -> DiagnosticReport:
        findings = []
        remediation = []

        mesh_root = Path(os.getenv("ORB_MESH_ROOT", os.getenv("ORB_SHARED_MESH_ROOT", "")))
        if not mesh_root or not mesh_root.exists():
            findings.append("Mesh root not configured or missing")
            remediation.append("Set ORB_MESH_ROOT or ORB_SHARED_MESH_ROOT environment variable")
            return DiagnosticReport("mesh", "critical", 0.3, findings, remediation)

        # Check manifest files
        manifests = ["service_registry.json", "api_manifest.json", "orb_permissions.json", "mesh_protocol.json"]
        missing = [m for m in manifests if not (mesh_root / "manifests" / m).exists()]
        if missing:
            findings.append(f"Missing manifests: {', '.join(missing)}")
            remediation.append("Run mesh initialization or restore from backup")

        # Check node discovery
        if hasattr(self.cali, 'mesh_traverser') and self.cali.mesh_traverser:
            nodes = self.cali.mesh_traverser.discovered_nodes
            if len(nodes) == 0:
                findings.append("No mesh nodes discovered")
                remediation.append("Run mesh discovery scan")
            else:
                stale = sum(1 for n in nodes.values() if (datetime.now() - n.last_seen) > timedelta(minutes=10))
                if stale > 0:
                    findings.append(f"{stale} stale nodes detected")
                    remediation.append("Investigate network connectivity for stale nodes")

        status = "healthy" if not findings else ("critical" if "not configured" in findings[0] else "degraded")
        return DiagnosticReport("mesh", status, 0.85 if status == "healthy" else 0.6, findings, remediation)

    def _probe_api_registry(self) -> DiagnosticReport:
        findings = []
        remediation = []

        registry_path = self.cali.cali_root / "config" / "api_registry.json"
        if not registry_path.exists():
            findings.append("API registry not found")
            remediation.append("Initialize api_registry.json from template")
            return DiagnosticReport("api_registry", "critical", 0.2, findings, remediation)

        try:
            with registry_path.open("r", encoding="utf-8") as f:
                registry = json.load(f)
            domain_count = len(registry.get("domains", []))
            entry_count = sum(len(d.get("entries", [])) for d in registry.get("domains", []))
            if domain_count == 0:
                findings.append("API registry has no domains")
                remediation.append("Populate registry with research API definitions")
            else:
                findings.append(f"Registry loaded: {domain_count} domains, {entry_count} entries")
        except Exception as exc:
            findings.append(f"Registry parse error: {exc}")
            remediation.append("Validate JSON syntax in api_registry.json")

        status = "healthy" if not any("error" in f.lower() or "not found" in f.lower() for f in findings) else "degraded"
        return DiagnosticReport("api_registry", status, 0.8, findings, remediation)

    def _probe_bulk_mirror(self) -> DiagnosticReport:
        findings = []
        remediation = []

        mirror_root = self.cali.bulk_mirror.BULK_MIRRORS_ROOT
        if not mirror_root.exists():
            findings.append("Bulk mirror directory not initialized")
            remediation.append("Create directory or run prefetch")
        else:
            categories = [d.name for d in mirror_root.iterdir() if d.is_dir()]
            if not categories:
                findings.append("No cached categories")
                remediation.append("Run bulk_mirror.prefetch_all() to seed caches")
            else:
                findings.append(f"Cached categories: {', '.join(categories)}")
                stale = 0
                for cat in categories:
                    if not self.cali.bulk_mirror.has_recent(cat):
                        stale += 1
                if stale > 0:
                    findings.append(f"{stale} stale categories")
                    remediation.append("Run refresh on stale categories")

        status = "healthy" if not any("not initialized" in f or "No cached" in f for f in findings) else "degraded"
        return DiagnosticReport("bulk_mirror", status, 0.75, findings, remediation)

    def _probe_knowledge_graph(self) -> DiagnosticReport:
        findings = []
        remediation = []

        kg = self.cali.kg
        node_count = kg.number_of_nodes()
        edge_count = kg.number_of_edges()

        findings.append(f"KG nodes: {node_count}, edges: {edge_count}")

        if node_count < 10:
            findings.append("Knowledge graph severely underpopulated")
            remediation.append("Inject substrate knowledge and cognitive seeds")
        elif node_count < 50:
            findings.append("Knowledge graph lightly populated")
            remediation.append("Continue substrate injection and pattern learning")

        # Check for orphaned nodes
        orphaned = [n for n in kg.nodes() if kg.in_degree(n) == 0 and n != "cali_identity"]
        if orphaned:
            findings.append(f"{len(orphaned)} orphaned nodes")
            remediation.append("Run self_prune to repair connections")

        status = "healthy" if not remediation else "warning"
        return DiagnosticReport("knowledge_graph", status, 0.8, findings, remediation)

    def _probe_patterns_db(self) -> DiagnosticReport:
        findings = []
        remediation = []

        try:
            with self.cali.db_lock:
                cursor = self.cali.patterns_db.cursor()
                cursor.execute("SELECT COUNT(*) FROM patterns")
                count = cursor.fetchone()[0]
                findings.append(f"Stored patterns: {count}")

                cursor.execute("SELECT COUNT(*) FROM patterns WHERE confidence < 0.3")
                low_conf = cursor.fetchone()[0]
                if low_conf > 100:
                    findings.append(f"{low_conf} low-confidence patterns (may indicate noise)")
                    remediation.append("Run self_prune to clean stale patterns")

                cursor.execute("SELECT AVG(confidence) FROM patterns")
                avg_conf = cursor.fetchone()[0]
                if avg_conf is not None:
                    findings.append(f"Average pattern confidence: {avg_conf:.3f}")
        except Exception as exc:
            findings.append(f"Pattern DB error: {exc}")
            remediation.append("Check database integrity")

        status = "healthy" if not remediation else "warning"
        return DiagnosticReport("patterns_db", status, 0.8, findings, remediation)

    def _probe_vaults(self) -> DiagnosticReport:
        findings = []
        remediation = []

        a_priori_count = len(self.cali.a_priori_vault.get("entries", []))
        a_posteriori_count = len(self.cali.a_posteriori_vault.get("entries", []))

        findings.append(f"A_priori entries: {a_priori_count}")
        findings.append(f"A_posteriori entries: {a_posteriori_count}")

        if a_priori_count < 5:
            findings.append("A_priori vault underpopulated")
            remediation.append("Inject default seeds and substrate knowledge")

        # Check vault files exist and are writable
        for vault_type in [MemoryType.A_PRIORI, MemoryType.A_POSTERIORI]:
            vault_path = self.cali.cali_root / "memory" / vault_type.value / "vault.jsonl"
            if not vault_path.exists():
                findings.append(f"{vault_type.value} vault file missing")
                remediation.append(f"Reinitialize {vault_type.value} vault")
            elif not os.access(vault_path, os.W_OK):
                findings.append(f"{vault_type.value} vault not writable")
                remediation.append("Check file permissions")

        status = "healthy" if not remediation else "warning"
        return DiagnosticReport("vaults", status, 0.85, findings, remediation)

    def _probe_encoder(self) -> DiagnosticReport:
        findings = []
        remediation = []

        encoder_name = type(self.cali.encoder).__name__
        findings.append(f"Encoder: {encoder_name}")

        if "Fallback" in encoder_name:
            findings.append("Using fallback encoder (sentence-transformers unavailable)")
            remediation.append("Install sentence-transformers for better embeddings")

        # Test encode
        try:
            test_vec = self.cali.encoder.encode("test")
            findings.append(f"Encoder output dim: {len(test_vec)}")
        except Exception as exc:
            findings.append(f"Encoder test failed: {exc}")
            remediation.append("Check encoder initialization")

        status = "healthy" if not remediation else "warning"
        return DiagnosticReport("encoder", status, 0.8, findings, remediation)

    def _probe_morb_system(self) -> DiagnosticReport:
        findings = []
        remediation = []

        if not hasattr(self.cali, 'morb_bridge') or self.cali.morb_bridge is None:
            findings.append("MORB bridge not initialized")
            remediation.append("Initialize MORBDeploymentBridge in CALI constructor")
            return DiagnosticReport("morb_system", "degraded", 0.4, findings, remediation)

        status_info = self.cali.morb_bridge.get_morb_status()
        findings.append(f"Active MORBs: {status_info['active_count']}")
        findings.append(f"MORB history: {status_info['history_count']}")

        if status_info['history_count'] == 0:
            findings.append("No MORB deployments recorded")
            remediation.append("Run initial MORB deployment test")

        status = "healthy" if not remediation else "warning"
        return DiagnosticReport("morb_system", status, 0.8, findings, remediation)

    def _probe_substrate_services(self) -> DiagnosticReport:
        findings = []
        remediation = []

        # Try to import and probe OrbSubstrateService
        try:
            from api.orb_substrate import OrbSubstrateService
            substrate = OrbSubstrateService()
            health = substrate.health_readiness()

            if health.get("manifest_validation_status", {}).get("valid"):
                findings.append("Substrate manifests valid")
            else:
                findings.append("Substrate manifests invalid or degraded")
                remediation.append("Check manifest files in orb_mesh/manifests/")

            if health.get("crm_db_reachable"):
                findings.append("CRM DB reachable")
            else:
                findings.append("CRM DB unreachable")
                remediation.append("Verify CRM database path and permissions")

            if health.get("prime_mail_db_reachable"):
                findings.append("Mail DB reachable")
            else:
                findings.append("Mail DB unreachable")
                remediation.append("Verify mail database path and permissions")

        except ImportError:
            findings.append("OrbSubstrateService not importable")
            remediation.append("Ensure api/orb_substrate.py is in Python path")
        except Exception as exc:
            findings.append(f"Substrate probe error: {exc}")
            remediation.append("Check substrate service configuration")

        status = "healthy" if not remediation else "degraded"
        return DiagnosticReport("substrate_services", status, 0.75, findings, remediation)

    def _report_to_dict(self, report: DiagnosticReport) -> Dict[str, Any]:
        return {
            "component": report.component,
            "status": report.status,
            "confidence": report.confidence,
            "findings": report.findings,
            "remediation": report.remediation,
            "timestamp": report.timestamp.isoformat(),
        }

    def _collect_remediations(self, reports: List[DiagnosticReport]) -> List[str]:
        """Collect unique remediation actions, prioritized by severity."""
        severity_order = {"critical": 0, "degraded": 1, "warning": 2, "healthy": 3}
        sorted_reports = sorted(reports, key=lambda r: severity_order.get(r.status, 4))
        seen = set()
        result = []
        for report in sorted_reports:
            for rem in report.remediation:
                if rem not in seen:
                    seen.add(rem)
                    result.append(f"[{report.status.upper()}] {report.component}: {rem}")
        return result

    def get_probe_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self._lock:
            return self.probe_history[-limit:]


# ═════════════════════════════════════════════════════════════════════════════
#  AGGRESSIVE LEARNING LOOP
# ═════════════════════════════════════════════════════════════════════════════

class AggressiveLearningLoop:
    """
    Continuous learning system that aggressively:
      1. Crystallizes high-confidence patterns into a_priori
      2. Cross-references substrate knowledge with research findings
      3. Builds predictive associations between domains
      4. Self-validates learned patterns against philosophical seeds
      5. Prunes noise and reinforces signal
    """

    def __init__(self, cali_instance: "CALISKG") -> None:
        self.cali = cali_instance
        self.learning_queue: deque[Dict[str, Any]] = deque(maxlen=1000)
        self.crystallization_threshold = 0.82
        self.reinforcement_threshold = 0.65
        self.prune_threshold = 0.25
        self._learning_active = True
        self._learning_thread: Optional[threading.Thread] = None
        self.learning_stats = {
            "patterns_crystallized": 0,
            "patterns_reinforced": 0,
            "patterns_pruned": 0,
            "associations_formed": 0,
            "last_run": None,
        }

    def start_background_learning(self) -> None:
        """Start the aggressive learning thread."""
        if self._learning_thread and self._learning_thread.is_alive():
            return
        self._learning_active = True
        self._learning_thread = threading.Thread(target=self._learning_loop, daemon=True)
        self._learning_thread.start()
        logger.info("Aggressive learning loop started")

    def stop_background_learning(self) -> None:
        self._learning_active = False

    def queue_observation(self, observation: Dict[str, Any]) -> None:
        """Queue an observation for learning processing."""
        observation["queued_at"] = datetime.now().isoformat()
        self.learning_queue.append(observation)

    def _learning_loop(self) -> None:
        """Background thread: process queued observations."""
        while self._learning_active:
            if not self.learning_queue:
                time.sleep(2)
                continue

            try:
                observation = self.learning_queue.popleft()
                self._process_observation(observation)
            except Exception as exc:
                logger.warning("Learning loop error: %s", exc)

            time.sleep(0.5)

    def _process_observation(self, observation: Dict[str, Any]) -> None:
        """Process a single observation through the learning pipeline."""
        obs_type = observation.get("type", "unknown")

        if obs_type == "research_result":
            self._learn_from_research(observation)
        elif obs_type == "morb_result":
            self._learn_from_morb(observation)
        elif obs_type == "user_interaction":
            self._learn_from_interaction(observation)
        elif obs_type == "mesh_health":
            self._learn_from_mesh(observation)
        elif obs_type == "pattern_validation":
            self._validate_pattern(observation)

    def _learn_from_research(self, observation: Dict[str, Any]) -> None:
        """Crystallize research findings into durable knowledge."""
        query = observation.get("query", "")
        synthesis = observation.get("synthesis", {})
        findings = synthesis.get("key_findings", [])
        confidence = synthesis.get("confidence_aggregate", 0.0)
        domains = observation.get("domains", [])

        if confidence >= self.crystallization_threshold and findings:
            # Create crystallized a_priori entry
            crystallized = {
                "type": "crystallized_research",
                "source": "aggressive_learning",
                "content": f"[Research:{confidence:.2f}] {'; '.join(findings[:3])}",
                "domain": domains[0] if domains else "general",
                "domains": domains,
                "confidence": confidence,
                "query_pattern": query,
                "timestamp": datetime.now().isoformat(),
            }
            self.cali.a_priori_vault["entries"].append(crystallized)

            # Add to KG
            node_id = f"crystal_{hashlib.sha256(crystallized['content'].encode()).hexdigest()[:12]}"
            self.cali.kg.add_node(node_id, type="crystallized_knowledge", domain=crystallized["domain"], confidence=confidence)
            self.cali.kg.add_edge("cali_identity", node_id, weight=confidence, relation="learned")
            self.cali.kg.add_edge("vault_a_priori", node_id, weight=0.9, relation="crystallized_from")

            self.learning_stats["patterns_crystallized"] += 1
            logger.info("Crystallized research pattern: %s...", query[:50])

            # Form cross-domain associations
            if len(domains) > 1:
                for i, d1 in enumerate(domains):
                    for d2 in domains[i+1:]:
                        assoc_id = f"assoc_{d1}_{d2}_{hashlib.sha256(query.encode()).hexdigest()[:8]}"
                        self.cali.kg.add_node(assoc_id, type="domain_association", domains=[d1, d2])
                        self.cali.kg.add_edge(f"domain_{d1}", assoc_id, weight=confidence * 0.8, relation="associates_with")
                        self.cali.kg.add_edge(f"domain_{d2}", assoc_id, weight=confidence * 0.8, relation="associates_with")
                        self.learning_stats["associations_formed"] += 1

        # Always store in patterns DB for inductive recall
        if findings:
            self.cali._remember_pattern(
                content=f"{query} -> {'; '.join(findings[:3])}",
                reasoning_mode=ReasoningMode.LOCKE_EMPIRICAL,
                confidence=min(confidence, 0.95),
                truth_likelihood=min(confidence * 0.9, 0.95),
                source="aggressive_learning_research",
            )

    def _learn_from_morb(self, observation: Dict[str, Any]) -> None:
        """Learn from MORB deployment outcomes."""
        morb_result = observation.get("morb_result", {})
        task_type = morb_result.get("task_type", "")
        verdict = morb_result.get("verdict", "")
        target_node = morb_result.get("target_node", "")

        # Learn node reliability
        reliability_key = f"node_reliability_{target_node}"
        existing = self.cali._retrieve_patterns(reliability_key, limit=1)
        if existing:
            old_conf = existing[0].confidence
            new_conf = old_conf * 0.9 + (1.0 if verdict == "PASS" else 0.0) * 0.1
            self.cali._remember_pattern(
                content=f"Node {target_node} reliability: {new_conf:.2f}",
                reasoning_mode=ReasoningMode.INDUCTIVE_STATISTICAL,
                confidence=new_conf,
                truth_likelihood=new_conf * 0.95,
                source="morb_learning",
            )
        else:
            self.cali._remember_pattern(
                content=f"Node {target_node} initial reliability: {1.0 if verdict == 'PASS' else 0.5}",
                reasoning_mode=ReasoningMode.INDUCTIVE_STATISTICAL,
                confidence=0.5,
                truth_likelihood=0.45,
                source="morb_learning",
            )

    def _learn_from_interaction(self, observation: Dict[str, Any]) -> None:
        """Learn from user interactions and feedback."""
        query = observation.get("query", "")
        response = observation.get("response", "")
        feedback = observation.get("feedback", "neutral")  # "positive", "negative", "neutral"

        if feedback == "positive":
            # Reinforce the pattern
            self.cali._remember_pattern(
                content=f"{query} -> {response}",
                reasoning_mode=ReasoningMode.KANT_SYNTHETIC,
                confidence=0.85,
                truth_likelihood=0.80,
                source="user_feedback_positive",
            )
            self.learning_stats["patterns_reinforced"] += 1
        elif feedback == "negative":
            # Mark pattern as low confidence
            self.cali._remember_pattern(
                content=f"{query} -> {response}",
                reasoning_mode=ReasoningMode.HUME_SKEPTICAL,
                confidence=0.2,
                truth_likelihood=0.15,
                source="user_feedback_negative",
            )

    def _learn_from_mesh(self, observation: Dict[str, Any]) -> None:
        """Learn from mesh health observations."""
        node_id = observation.get("node_id", "")
        health_status = observation.get("health_status", "")
        load_factor = observation.get("load_factor", 0.0)

        # Learn node behavior patterns
        self.cali._remember_pattern(
            content=f"Node {node_id} status={health_status} load={load_factor:.2f}",
            reasoning_mode=ReasoningMode.INDUCTIVE_STATISTICAL,
            confidence=0.7,
            truth_likelihood=0.65,
            source="mesh_observation",
        )

    def _validate_pattern(self, observation: Dict[str, Any]) -> None:
        """Validate an existing pattern against philosophical seeds."""
        pattern_id = observation.get("pattern_id", "")
        # This would cross-reference with Core-4 seeds
        # For now, mark as validated
        pass

    def run_aggressive_prune(self) -> Dict[str, Any]:
        """Aggressively prune low-confidence, stale patterns."""
        cutoff = (datetime.now() - timedelta(days=14)).isoformat()
        with self.cali.db_lock:
            cursor = self.cali.patterns_db.cursor()
            # Prune low confidence AND old
            cursor.execute(
                "DELETE FROM patterns WHERE timestamp < ? AND confidence < ?",
                (cutoff, self.prune_threshold),
            )
            removed = cursor.rowcount
            # Also prune user-negative feedback patterns
            cursor.execute(
                "DELETE FROM patterns WHERE source = ? AND confidence < ?",
                ("user_feedback_negative", 0.3),
            )
            removed += cursor.rowcount
            self.cali.patterns_db.commit()
            cursor.execute("VACUUM")
            self.cali.patterns_db.commit()

        self.learning_stats["patterns_pruned"] += removed
        self.learning_stats["last_run"] = datetime.now().isoformat()

        # Repair orphaned KG nodes
        orphaned = [node for node in self.cali.kg.nodes() if self.cali.kg.in_degree(node) == 0 and node != "cali_identity"]
        for node in orphaned:
            self.cali.kg.add_edge("cali_identity", node, weight=0.3, relation="repaired_connection")

        return {
            "removed_patterns": removed,
            "repaired_nodes": len(orphaned),
            "stats": dict(self.learning_stats),
            "timestamp": datetime.now().isoformat(),
        }

    def get_learning_stats(self) -> Dict[str, Any]:
        return dict(self.learning_stats)


# ═════════════════════════════════════════════════════════════════════════════
#  MAIN CALI SKG CLASS
# ═════════════════════════════════════════════════════════════════════════════

class CALISKG:
    """CALI: Cognitively Aligned Linear Intelligence — v3.5 Aggressive Learning Edition."""

    PHILOSOPHER_SEEDS = {
        "locke": PhilosophicalSeed(
            name="John Locke",
            logic_type=ReasoningMode.LOCKE_EMPIRICAL,
            weight_formula="sensory_evidence * reliability",
            confidence_bias=0.7,
            description="All knowledge comes from sensory experience. Tabula rasa.",
        ),
        "hume": PhilosophicalSeed(
            name="David Hume",
            logic_type=ReasoningMode.HUME_SKEPTICAL,
            weight_formula="impression_strength * constant_conjunction",
            confidence_bias=0.4,
            description="Causal connections are habits of mind, not necessary truths.",
        ),
        "kant": PhilosophicalSeed(
            name="Immanuel Kant",
            logic_type=ReasoningMode.KANT_SYNTHETIC,
            weight_formula="a_priori_categories * empirical_intuitions",
            confidence_bias=0.8,
            description="Knowledge requires both a priori forms and a posteriori content.",
        ),
        "spinoza": PhilosophicalSeed(
            name="Baruch Spinoza",
            logic_type=ReasoningMode.SPINOZA_MONISTIC,
            weight_formula="geometric_necessity * adequate_ideas",
            confidence_bias=0.9,
            description="God and Nature are one substance. Geometric method.",
        ),
    }

    SYSTEM_LOGICS = {
        "inductive": ReasoningMode.INDUCTIVE_STATISTICAL,
        "deductive": ReasoningMode.DEDUCTIVE_LOGICAL,
        "intuitive": ReasoningMode.INTUITIVE_HOLISTIC,
    }

    DEFAULT_A_PRIORI_ENTRIES = [
        {"content": "Identity is stable enough for reasoning when a subject remains itself."},
        {"content": "A contradiction cannot be true in the same respect at the same time."},
        {"content": "Causes and effects should be tested against observation before certainty is claimed."},
        {"content": "Time orders experience, and experience refines judgment."},
    ]

    DOMAIN_HINTS = {
        "space": {"space", "astronomy", "rocket", "planet", "nasa", "spacex", "asteroid"},
        "weather": {"weather", "storm", "forecast", "temperature", "hurricane", "rain"},
        "biomedical": {"medical", "disease", "clinical", "trial", "pubmed", "biology"},
        "finance": {
            "stock", "market", "economic", "finance", "fred", "inflation",
            "gaap", "ifrs", "accounting", "reporting", "audit", "filing",
            "risk", "valuation", "dcf", "var", "sharpe", "compliance",
            "sec", "regulatory", "disclosure", "revenue", "billing",
            "corporate", "governance", "truemark", "goat", "spruked",
        },
        "academic": {"paper", "research", "study", "scholar", "academic", "openalex"},
        "geospatial": {"map", "earthquake", "location", "geospatial", "seismic"},
    }

    SUBSTRATE_ROOT = r_drive_path("CALI_SUBSTRATE", "domain_knowledge")
    COGNITIVE_SEED_ROOT = r_drive_path("CALI_SUBSTRATE", "seeds", "cognitive_seed_vault")

    def __init__(self, system_path: Path, partition_size_gb: int = 20) -> None:
        self.instance_id = os.getenv("ORB_INSTANCE_ID", "wsl").strip() or "wsl"
        self.shared_mesh_root = os.getenv("ORB_SHARED_MESH_ROOT")
        self.system_path = Path(system_path).expanduser().resolve()
        self.partition_size = partition_size_gb * 1024 * 1024 * 1024
        self.cali_root = self.system_path / "CALI_System"
        self._initialize_system_structure()
        self.core4_seed_entries = self._load_core4_seed_entries()

        self.device = self._resolve_device()
        self.vram_gb = 6 if torch is not None and hasattr(torch, "cuda") and torch.cuda.is_available() else 0
        self.encoder = self._initialize_encoder()
        self.encoder_backend = type(self.encoder).__name__

        self.cochlea = AdaptiveCochlearProcessor()
        self.advisory = SoftMaxAdvisorySKG()
        self.bulk_mirror = BulkMirrorCache()
        self.swarm = CALISwarmOrchestrator(
            self.cali_root / "config" / "api_registry.json",
            bulk_mirror=self.bulk_mirror,
        )

        # ── NEW: MORB Deployment Bridge ───────────────────────────────────────
        mesh_root = Path(os.getenv("ORB_MESH_ROOT", os.getenv("ORB_SHARED_MESH_ROOT", "R:/R_Drive_Substrate/orb_mesh")))
        self.morb_bridge = MORBDeploymentBridge(mesh_root, self)

        # ── NEW: Substrate Mesh Traverser ────────────────────────────────────
        self.mesh_traverser = SubstrateMeshTraverser(mesh_root, self)

        # ── NEW: Diagnostic Probe System ─────────────────────────────────────
        self.diagnostic_system = DiagnosticProbeSystem(self)

        # ── NEW: Aggressive Learning Loop ────────────────────────────────────
        self.learning_loop = AggressiveLearningLoop(self)
        self.learning_loop.start_background_learning()

        self.a_priori_vault = self._initialize_vault(MemoryType.A_PRIORI)
        self.a_posteriori_vault = self._initialize_vault(MemoryType.A_POSTERIORI)

        self.kg = nx.DiGraph() if nx is not None else _SimpleDiGraph()
        self._build_core_cognition_graph()

        self.db_lock = threading.Lock()
        self.patterns_db = sqlite3.connect(self.cali_root / "memory" / "patterns.db", check_same_thread=False)
        self._initialize_patterns_db()

        self.voice_config = {
            "engine": "qwen3-tts",
            "qwen3_tts_endpoint": os.getenv("QWEN3_TTS_ENDPOINT", "http://127.0.0.1:8020"),
            "voice_path": "voices/af_bella.bin",
            "speaker_id": "af_bella",
            "backup_engine": "kokoro",
            "backup_voice": "af_sky",
            "speed": 0.95,
            "pitch": 0.1,
            "emotion": "thoughtful_warm",
            "gpu_accelerated": str(self.device) == "cuda",
        }

        self._inject_substrate_knowledge()
        self._load_cognitive_seed_vaults()

        _prefetch_thread = threading.Thread(
            target=self._background_prefetch,
            name="cali-bulk-mirror-prefetch",
            daemon=True,
        )
        _prefetch_thread.start()

        self.current_reasoning_mode = ReasoningMode.KANT_SYNTHETIC
        self.confidence_threshold = 0.75
        self.interaction_count = 0
        self.orb_state = {
            "skin": "default_crystalline",
            "swarm_visible": False,
            "desktop_access": True,
            "browser_access": True,
            "voice_active": True,
            "llm_route": os.getenv("ORB_LLM_ROUTE", "local"),
            "llm_local_endpoint": os.getenv("ORB_LOCAL_LLM_ENDPOINT", "http://127.0.0.1:11434"),
            "llm_local_model": os.getenv("ORB_LOCAL_LLM_MODEL", "llama3.2:1b"),
            "llm_api_base": "",
            "llm_api_model": "",
            "llm_api_key": "",
            "llm_governance_wrapper": os.getenv("ORB_LLM_GOVERNANCE_WRAPPER", "0").strip().lower() in {"1", "true", "yes", "on"},
            "llm_retain_voice": os.getenv("ORB_LLM_RETAIN_VOICE", "1").strip().lower() in {"1", "true", "yes", "on"},
            # ── NEW: v3.5 state fields ──────────────────────────────────────
            "morb_deployment_enabled": True,
            "mesh_traversal_enabled": True,
            "aggressive_learning_enabled": True,
            "auto_diagnostics_enabled": True,
            "diagnostic_interval_minutes": 30,
        }

        # Start auto-diagnostics if enabled
        if self.orb_state["auto_diagnostics_enabled"]:
            self._start_auto_diagnostics()

        logger.info("CALI SKG v3.5 initialized | Device: %s | Partition: %sGB | MORB: %s | Mesh: %s | Learning: %s",
                    self.device, partition_size_gb,
                    "active" if self.morb_bridge else "inactive",
                    "active" if self.mesh_traverser else "inactive",
                    "active" if self.learning_loop else "inactive")

    def _start_auto_diagnostics(self) -> None:
        """Start background auto-diagnostics thread."""
        def diagnostic_worker():
            interval = self.orb_state.get("diagnostic_interval_minutes", 30) * 60
            while self.orb_state.get("auto_diagnostics_enabled", False):
                time.sleep(interval)
                try:
                    report = self.diagnostic_system.full_system_probe()
                    if report["overall_status"] in ("critical", "degraded"):
                        logger.warning("Auto-diagnostic detected %s status: %s",
                                       report["overall_status"],
                                       report["top_remediations"][:3])
                        # Queue learning observation
                        self.learning_loop.queue_observation({
                            "type": "mesh_health",
                            "overall_status": report["overall_status"],
                            "components": report["summary"],
                        })
                except Exception as exc:
                    logger.warning("Auto-diagnostic error: %s", exc)

        thread = threading.Thread(target=diagnostic_worker, name="cali-auto-diagnostics", daemon=True)
        thread.start()
        logger.info("Auto-diagnostics started (interval: %d min)", self.orb_state.get("diagnostic_interval_minutes", 30))

    def _initialize_system_structure(self) -> None:
        for relative in (
            "memory/a_priori",
            "memory/a_posteriori",
            "memory/patterns",
            "config",
            "cache",
            "logs",
            "voice_cache",
            "swarm_results",
            "morb_logs",
            "diagnostics",
        ):
            (self.cali_root / relative).mkdir(parents=True, exist_ok=True)

    def _resolve_device(self) -> Any:
        if torch is None:
            return "cpu"
        if hasattr(torch, "cuda") and torch.cuda.is_available():
            return torch.device("cuda")
        return torch.device("cpu")

    def _initialize_encoder(self) -> Any:
        if SentenceTransformer is None:
            logger.warning("sentence-transformers unavailable; using fallback encoder")
            return FallbackSentenceEncoder()

        cache_dir = self.cali_root / "cache" / "sentence_transformers"
        cache_dir.mkdir(parents=True, exist_ok=True)
        encoder_mode = os.getenv("CALI_ENCODER_MODE", "fallback").strip().lower()
        if encoder_mode in {"", "fallback", "local_fallback", "off"}:
            logger.info("CALI encoder using deterministic fallback backend")
            return FallbackSentenceEncoder()

        allow_download = os.getenv("CALI_ALLOW_MODEL_DOWNLOAD", "0").strip().lower() in {"1", "true", "yes", "on"}
        model_name = os.getenv("CALI_SENTENCE_MODEL", "all-MiniLM-L6-v2").strip() or "all-MiniLM-L6-v2"

        kwargs = {
            "device": str(self.device),
            "cache_folder": str(cache_dir),
        }

        if not allow_download:
            kwargs["local_files_only"] = True

        try:
            return SentenceTransformer(model_name, **kwargs)
        except TypeError:
            kwargs.pop("local_files_only", None)
            if not allow_download:
                logger.warning("SentenceTransformer local-only option unsupported; using fallback encoder")
                return FallbackSentenceEncoder()
            try:
                return SentenceTransformer(model_name, **kwargs)
            except Exception as exc:
                logger.warning("SentenceTransformer init failed (%s); using fallback encoder", exc)
                return FallbackSentenceEncoder()
        except Exception as exc:
            logger.warning("SentenceTransformer init failed (%s); using fallback encoder", exc)
            return FallbackSentenceEncoder()

    def _load_core4_seed_entries(self) -> List[Dict[str, Any]]:
        seeds_dir = Path(__file__).resolve().parent / "components" / "core_4_minds"
        seed_files = [
            seeds_dir / "hlocke" / "locke_empiricism_skg.json",
            seeds_dir / "hhume" / "hume_skepticism_skg.json",
            seeds_dir / "ikant" / "kant_critical_skg.json",
            seeds_dir / "bspinoza" / "spinoza_monism_skg.json",
        ]

        entries: List[Dict[str, Any]] = []
        for path in seed_files:
            if not path.exists():
                continue
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                meta = payload.get("skg_metadata", {})
                philosopher = meta.get("philosopher") or path.stem

                core = payload.get("core_axiom", {})
                if core:
                    entries.append({
                        "type": "core_axiom",
                        "philosopher": philosopher,
                        "source": path.name,
                        "node_id": core.get("node_id"),
                        "label": core.get("label"),
                        "definition": core.get("definition"),
                        "properties": core.get("properties", {}),
                    })

                for node in payload.get("concept_nodes", []) or []:
                    entries.append({
                        "type": "concept",
                        "philosopher": philosopher,
                        "source": path.name,
                        "node_id": node.get("node_id"),
                        "label": node.get("label"),
                        "category": node.get("category"),
                        "definition": node.get("properties", {}).get("definition"),
                        "properties": node.get("properties", {}),
                        "relationships": node.get("relationships", {}),
                    })

                for rule in payload.get("reasoning_rules", []) or []:
                    entries.append({
                        "type": "reasoning_rule",
                        "philosopher": philosopher,
                        "source": path.name,
                        "rule_id": rule.get("rule_id"),
                        "name": rule.get("name"),
                        "priority": rule.get("priority"),
                        "logic": rule.get("logic"),
                        "condition": rule.get("condition"),
                        "action": rule.get("action"),
                    })

                for flow in payload.get("reasoning_flow_templates", []) or []:
                    entries.append({
                        "type": "reasoning_flow",
                        "philosopher": philosopher,
                        "source": path.name,
                        "template_id": flow.get("template_id") or flow.get("name"),
                        "steps": flow.get("steps", []),
                    })

                taxonomies = payload.get("hierarchical_taxonomies")
                if isinstance(taxonomies, list):
                    for tax in taxonomies:
                        entries.append({
                            "type": "taxonomy",
                            "philosopher": philosopher,
                            "source": path.name,
                            "name": tax.get("name"),
                            "levels": tax.get("levels"),
                        })
                elif isinstance(taxonomies, dict):
                    for name, body in taxonomies.items():
                        entries.append({
                            "type": "taxonomy",
                            "philosopher": philosopher,
                            "source": path.name,
                            "name": name,
                            "levels": body,
                        })
            except Exception as exc:
                logger.warning("Failed to load core4 seed %s: %s", path, exc)
                continue
        return entries

    def _initialize_vault(self, vault_type: MemoryType) -> Dict[str, Any]:
        vault_path = self.cali_root / "memory" / vault_type.value
        vault_file = vault_path / "vault.jsonl"
        entries = self._load_vault_entries(vault_file)

        if vault_type == MemoryType.A_PRIORI and not entries:
            entries = [dict(item) for item in self.DEFAULT_A_PRIORI_ENTRIES + self.core4_seed_entries]
            with vault_file.open("w", encoding="utf-8") as handle:
                for entry in entries:
                    handle.write(json.dumps(entry) + "\n")

        return {
            "type": vault_type,
            "path": vault_file,
            "entries": entries,
            "immutable": vault_type == MemoryType.A_PRIORI,
        }

    def _load_vault_entries(self, vault_file: Path) -> List[Dict[str, Any]]:
        if not vault_file.exists():
            return []

        entries: List[Dict[str, Any]] = []
        with vault_file.open("r", encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed vault entry in %s", vault_file)
        return entries

    def _initialize_patterns_db(self) -> None:
        with self.db_lock:
            cursor = self.patterns_db.cursor()
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS patterns (
                    id TEXT PRIMARY KEY,
                    content TEXT,
                    reasoning_mode TEXT,
                    confidence REAL,
                    truth_likelihood REAL,
                    timestamp TEXT,
                    source TEXT,
                    use_count INTEGER,
                    last_validated TEXT,
                    embedding BLOB
                )
                """
            )
            self.patterns_db.commit()

    def _build_core_cognition_graph(self) -> None:
        self.kg.add_node("cali_identity", type="cognitive_entity", name="CALI", stability="immutable")

        for seed_id, seed in self.PHILOSOPHER_SEEDS.items():
            self.kg.add_node(f"seed_{seed_id}", type="philosophical_logic", seed_data=seed.to_dict())
            self.kg.add_edge("cali_identity", f"seed_{seed_id}", weight=0.25, relation="reasons_with")

        self.kg.add_node("vault_a_priori", type="memory", mutability="immutable", access="direct")
        self.kg.add_node("vault_a_posteriori", type="memory", mutability="append_only", access="experiential")
        self.kg.add_node("acp_cochlea", type="perception", modality="auditory", human_like=True)
        self.kg.add_node("softmax_advisory", type="meta_cognition", function="confidence_arbitration")
        self.kg.add_node("swarm_orchestrator", type="action", modality="research", visual_metaphor="orb_swarm")
        self.kg.add_node("voice_synthesis", type="expression", primary=True, fallback="text")

        # ── NEW: v3.5 system nodes ───────────────────────────────────────────
        self.kg.add_node("morb_bridge", type="deployment", function="deterministic_evaluation")
        self.kg.add_node("mesh_traverser", type="topology", function="node_discovery")
        self.kg.add_node("diagnostic_system", type="health", function="system_probe")
        self.kg.add_node("learning_loop", type="cognition", function="aggressive_learning")

        for node in (
            "vault_a_priori",
            "vault_a_posteriori",
            "acp_cochlea",
            "softmax_advisory",
            "swarm_orchestrator",
            "voice_synthesis",
            "morb_bridge",
            "mesh_traverser",
            "diagnostic_system",
            "learning_loop",
        ):
            self.kg.add_edge("cali_identity", node, weight=0.9, relation="embodies")

    def reason(self, query: str, context: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self.interaction_count += 1
        context = context or {}
        reasoning_outputs: List[Dict[str, Any]] = []

        for seed in self.PHILOSOPHER_SEEDS.values():
            reasoning_outputs.append(self._apply_philosophical_logic(query, seed, context))

        reasoning_outputs.append(self._apply_inductive_logic(query, context))
        reasoning_outputs.append(self._apply_deductive_logic(query, context))
        reasoning_outputs.append(self._apply_intuitive_logic(query, context))

        advisory = self.advisory.compute_verdict(reasoning_outputs)
        response_text = self._formulate_response(query, advisory, reasoning_outputs)

        self._store_experience(query, reasoning_outputs, advisory)
        self._remember_pattern(
            content=f"{query} -> {response_text}",
            reasoning_mode=self._resolve_top_reasoning_mode(advisory, reasoning_outputs),
            confidence=advisory["confidence"],
            truth_likelihood=advisory["truth_likelihood"],
            source="internal_reasoning",
        )

        # Queue for aggressive learning
        self.learning_loop.queue_observation({
            "type": "user_interaction",
            "query": query,
            "response": response_text,
            "confidence": advisory["confidence"],
            "feedback": context.get("feedback", "neutral"),
        })

        return {
            "query": query,
            "philosophical_reasoning": reasoning_outputs,
            "advisory_verdict": advisory,
            "recommended_response": response_text,
            "voice_ready": True,
            "timestamp": datetime.now().isoformat(),
        }


    def _apply_philosophical_logic(self, query: str, seed: PhilosophicalSeed, context: Dict[str, Any]) -> Dict[str, Any]:
        evidence = self._retrieve_a_posteriori(query, limit=5)
        a_priori = self._retrieve_a_priori(query)

        if seed.logic_type == ReasoningMode.LOCKE_EMPIRICAL:
            confidence = seed.confidence_bias * min(1.0, len(evidence) / 4 if evidence else 0.35)
        elif seed.logic_type == ReasoningMode.HUME_SKEPTICAL:
            has_causal_language = any(word in query.lower() for word in ("cause", "because", "therefore"))
            confidence = seed.confidence_bias * (0.5 if has_causal_language else 0.95)
        elif seed.logic_type == ReasoningMode.KANT_SYNTHETIC:
            synthesis = len(a_priori) + len(evidence)
            confidence = seed.confidence_bias * min(1.0, max(synthesis, 1) / 4)
        else:
            confidence = seed.confidence_bias * (1.0 if a_priori else 0.6)

        return {
            "philosopher": seed.name,
            "logic_type": seed.logic_type.name,
            "raw_confidence": float(np.clip(confidence, 0, 1)),
            "truth_estimate": float(np.clip(confidence * 0.9, 0, 1)),
            "accuracy": float(np.clip(confidence, 0, 1)),
            "reasoning_trace": f"{seed.name} reasoning applied with {seed.weight_formula}",
            "evidence_count": len(evidence),
            "context_keys": list(context.keys())[:5],
        }

    def _apply_inductive_logic(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        patterns = self._retrieve_patterns(query, limit=5)
        confidence = 0.6 + (0.08 * len(patterns)) if patterns else 0.5
        return {
            "philosopher": "Inductive_Statistical",
            "logic_type": ReasoningMode.INDUCTIVE_STATISTICAL.name,
            "raw_confidence": float(min(0.9, confidence)),
            "truth_estimate": float(min(0.85, confidence)),
            "accuracy": float(min(0.9, confidence)),
            "pattern_count": len(patterns),
        }

    def _apply_deductive_logic(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        premises = self._retrieve_a_priori(query)
        confidence = 0.9 if premises else 0.4
        return {
            "philosopher": "Deductive_Logical",
            "logic_type": ReasoningMode.DEDUCTIVE_LOGICAL.name,
            "raw_confidence": confidence,
            "truth_estimate": confidence,
            "accuracy": confidence,
            "premise_count": len(premises),
        }

    def _apply_intuitive_logic(self, query: str, context: Dict[str, Any]) -> Dict[str, Any]:
        query_embedding = np.asarray(self.encoder.encode(query), dtype=np.float32)
        patterns = self._retrieve_patterns(query, limit=10)

        similarity_scores: List[float] = []
        for pattern in patterns:
            if pattern.embedding is None:
                continue
            similarity_scores.append(self._cosine_similarity(query_embedding, pattern.embedding))

        similarity = max(similarity_scores) if similarity_scores else 0.45
        confidence = float(np.clip(0.55 + (similarity * 0.35), 0, 0.92))
        return {
            "philosopher": "Intuitive_Holistic",
            "logic_type": ReasoningMode.INTUITIVE_HOLISTIC.name,
            "raw_confidence": confidence,
            "truth_estimate": float(np.clip(confidence * 0.95, 0, 1)),
            "accuracy": confidence,
            "gestalt_match": "holistic_similarity_detected",
            "similarity": similarity,
        }

    def _retrieve_a_priori(self, query: str) -> List[str]:
        return self._retrieve_vault_matches(self.a_priori_vault["entries"], query, limit=3)

    def _retrieve_a_posteriori(self, query: str, limit: int = 5) -> List[str]:
        return self._retrieve_vault_matches(self.a_posteriori_vault["entries"], query, limit=limit)

    def _retrieve_vault_matches(self, entries: List[Dict[str, Any]], query: str, limit: int) -> List[str]:
        ranked: List[tuple[float, str]] = []
        for entry in entries:
            content = str(entry.get("content", ""))
            score = self._score_text_match(query, content)
            if score > 0:
                ranked.append((score, content))
        ranked.sort(key=lambda item: item[0], reverse=True)
        return [content for _, content in ranked[:limit]]

    def _retrieve_patterns(self, query: str, limit: int = 5) -> List[LearnedPattern]:
        with self.db_lock:
            cursor = self.patterns_db.cursor()
            cursor.execute(
                "SELECT * FROM patterns WHERE content LIKE ? ORDER BY confidence DESC LIMIT ?",
                (f"%{query}%", limit),
            )
            rows = cursor.fetchall()
        return [self._row_to_pattern(row) for row in rows]

    def _row_to_pattern(self, row: Any) -> LearnedPattern:
        embedding = pickle.loads(row[9]) if row[9] is not None else None
        return LearnedPattern(
            pattern_id=row[0],
            content=row[1],
            reasoning_mode=ReasoningMode[row[2]],
            confidence=row[3],
            truth_likelihood=row[4],
            timestamp=datetime.fromisoformat(row[5]),
            source=row[6],
            use_count=row[7],
            last_validated=datetime.fromisoformat(row[8]) if row[8] else None,
            embedding=embedding,
        )

    def _remember_pattern(self, content: str, reasoning_mode: ReasoningMode, confidence: float,
                          truth_likelihood: float, source: str) -> None:
        timestamp = datetime.now()
        embedding = pickle.dumps(np.asarray(self.encoder.encode(content), dtype=np.float32))
        pattern = LearnedPattern(
            pattern_id="",
            content=content,
            reasoning_mode=reasoning_mode,
            confidence=confidence,
            truth_likelihood=truth_likelihood,
            timestamp=timestamp,
            source=source,
            last_validated=timestamp,
        )

        with self.db_lock:
            cursor = self.patterns_db.cursor()
            cursor.execute(
                """
                INSERT OR REPLACE INTO patterns (
                    id, content, reasoning_mode, confidence, truth_likelihood,
                    timestamp, source, use_count, last_validated, embedding
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    pattern.pattern_id,
                    pattern.content,
                    pattern.reasoning_mode.name,
                    pattern.confidence,
                    pattern.truth_likelihood,
                    pattern.timestamp.isoformat(),
                    pattern.source,
                    pattern.use_count,
                    pattern.last_validated.isoformat() if pattern.last_validated else None,
                    embedding,
                ),
            )
            self.patterns_db.commit()

    def _store_experience(self, query: str, reasoning: List[Dict[str, Any]], advisory: Dict[str, Any]) -> None:
        entry = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "reasoning_summary": [item["philosopher"] for item in reasoning],
            "advisory_confidence": advisory["confidence"],
            "content": f"Query: {query} | Confidence: {advisory['confidence']:.2f}",
        }
        self.a_posteriori_vault["entries"].append(entry)
        with self.a_posteriori_vault["path"].open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

    def _store_research_return(self, query: str, synthesis: Dict[str, Any], raw_results: List[Dict[str, Any]]) -> None:
        weighted_vals = [
            r["weighted_confidence"]
            for r in raw_results
            if r.get("weighted_confidence") is not None and not r.get("error")
        ]
        if weighted_vals:
            confidence = float(np.mean(weighted_vals))
            truth_likelihood = round(confidence * 0.90, 4)
        else:
            confidence = float(synthesis.get("confidence_aggregate", 0.60))
            truth_likelihood = round(confidence * 0.90, 4)

        confidence = round(max(0.35, min(0.95, confidence)), 4)
        findings = synthesis.get("key_findings") or []
        finding_text = "; ".join(str(f) for f in findings[:3]) if findings else "(no findings)"

        entry = {
            "timestamp": datetime.now().isoformat(),
            "query": query,
            "source": "swarm_research",
            "domains": synthesis.get("domains", []),
            "sources_queried": synthesis.get("sources_queried", 0),
            "successful_returns": synthesis.get("successful_returns", 0),
            "key_findings_summary": finding_text,
            "advisory_confidence": confidence,
            "truth_likelihood": truth_likelihood,
            "content": f"Research: {query} | Findings: {finding_text} | Confidence: {confidence:.3f}",
        }
        self.a_posteriori_vault["entries"].append(entry)
        with self.a_posteriori_vault["path"].open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

        self._remember_pattern(
            content=f"{query} -> {finding_text}",
            reasoning_mode=ReasoningMode.LOCKE_EMPIRICAL,
            confidence=confidence,
            truth_likelihood=truth_likelihood,
            source="swarm_research",
        )

        if confidence >= 0.82 and findings:
            crystallized = {
                "row_id": f"crystal_{hash(query) & 0xFFFFFFFF}",
                "source": "crystallized_research",
                "content": f"[Research:{confidence:.2f}] {finding_text}",
                "domain": (synthesis.get("domains") or ["general"])[0],
                "timestamp": datetime.now().isoformat(),
            }
            self.a_priori_vault["entries"].append(crystallized)
            logger.info("Crystallized high-confidence research (%.3f) into a_priori vault: %s", confidence, query[:60])

    def _resolve_top_reasoning_mode(self, advisory: Dict[str, Any], reasoning: List[Dict[str, Any]]) -> ReasoningMode:
        weights = advisory.get("weights") or []
        if not weights:
            return ReasoningMode.KANT_SYNTHETIC

        top_index = int(np.argmax(weights))
        top_logic = reasoning[top_index].get("logic_type", ReasoningMode.KANT_SYNTHETIC.name)
        return ReasoningMode[top_logic]

    def _formulate_response(self, query: str, advisory: Dict[str, Any], reasoning: List[Dict[str, Any]]) -> str:
        confidence = advisory["confidence"]

        if confidence > 0.8:
            certainty = "I am confident that"
        elif confidence > 0.6:
            certainty = "I believe that"
        elif confidence > 0.4:
            certainty = "It seems possible that"
        else:
            certainty = "I am uncertain, but consider that"

        if advisory.get("weights"):
            top_index = int(np.argmax(advisory["weights"]))
            top_reasoning = reasoning[top_index]
            philosopher = top_reasoning["philosopher"]
            clause = f"{philosopher} offers the strongest frame for '{query}'."
        else:
            clause = f"further investigation is needed for '{query}'."

        if advisory.get("tension_detected"):
            clause += " Internal disagreement is high, so confidence is temporarily capped while more evidence accumulates."

        return f"{certainty} {clause}"

    # ── RESEARCH ─────────────────────────────────────────────────────────────

    async def hear(self, audio_signal: np.ndarray) -> Dict[str, Any]:
        features = self.cochlea.process_audio(audio_signal)
        should_respond = features["attention_salience"] > 0.3
        return {
            "perceptual_features": features,
            "understood": should_respond,
            "attention_level": features["attention_salience"],
            "ready_for_reasoning": should_respond,
        }

    async def research(self, query: str, domains: Optional[List[str]] = None) -> Dict[str, Any]:
        if not self.swarm.api_registry and self.swarm.api_registry_path.exists():
            self.swarm.api_registry = self.swarm._load_api_registry(self.swarm.api_registry_path)

        if not self.swarm.api_registry:
            return {
                "task_id": None,
                "research_synthesis": {"error": "No API registry loaded"},
                "voice_response": "I do not have a research registry configured yet.",
                "swarm_visual_state": "idle",
                "timestamp": datetime.now().isoformat(),
            }

        selected_domains = domains or self._infer_domains(query)

        mirror_snippets = self.bulk_mirror.summarize_for_query(query, selected_domains)
        if mirror_snippets:
            logger.info("BulkMirror cache hit for query '%s': %d snippets", query[:50], len(mirror_snippets))

        await self.swarm.initialize()
        self.set_orb_state("swarm_visible", True)
        task_id = await self.swarm.spawn_research_orbs(query, selected_domains)
        synthesis = await self.swarm.ingest_results(task_id)

        if mirror_snippets:
            existing = synthesis.get("key_findings") or []
            synthesis["key_findings"] = [f"[CACHED] {s}" for s in mirror_snippets[:2]] + existing
            synthesis["bulk_mirror_hits"] = len(mirror_snippets)

        swarm_task = self.swarm.active_tasks.get(task_id)
        raw_results = swarm_task.results if swarm_task else []

        synthesis["domains"] = selected_domains
        self._store_research_return(query, synthesis, raw_results)

        # Queue for aggressive learning
        self.learning_loop.queue_observation({
            "type": "research_result",
            "query": query,
            "synthesis": synthesis,
            "domains": selected_domains,
        })

        voice_response = self._articulate_research(synthesis)
        self.set_orb_state("swarm_visible", False)
        return {
            "task_id": task_id,
            "domains": selected_domains,
            "research_synthesis": synthesis,
            "voice_response": voice_response,
            "swarm_visual_state": "ingested",
            "bulk_mirror_snippets": mirror_snippets,
            "timestamp": datetime.now().isoformat(),
        }

    def _infer_domains(self, query: str) -> List[str]:
        lowered = query.lower()
        matches = [
            domain
            for domain, keywords in self.DOMAIN_HINTS.items()
            if any(keyword in lowered for keyword in keywords)
        ]
        return matches or list(self.DOMAIN_HINTS.keys())[:2]

    def _articulate_research(self, synthesis: Dict[str, Any]) -> str:
        findings = synthesis.get("key_findings", [])
        count = synthesis.get("successful_returns", 0)

        if not findings:
            return "I've searched the available sources, but found no definitive information on that topic."

        intro = f"I've consulted {count} sources. "
        body = " ".join(findings[:3])
        return intro + body

    # ── MORB DEPLOYMENT API ──────────────────────────────────────────────────

    def deploy_morb(self, task_type: str, predicate: str, target_node: str,
                    parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Public API: Deploy a single MORB for deterministic evaluation."""
        if not self.orb_state.get("morb_deployment_enabled", False):
            return {"error": "MORB deployment disabled in orb_state", "morb_id": None}
        result = self.morb_bridge.deploy_morb(task_type, predicate, target_node, parameters)
        self.learning_loop.queue_observation({"type": "morb_result", "morb_result": result})
        return result

    def deploy_morb_swarm(self, task_type: str, predicate: str, target_nodes: List[str],
                          parameters: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Public API: Deploy MORBs across multiple nodes."""
        if not self.orb_state.get("morb_deployment_enabled", False):
            return {"error": "MORB deployment disabled in orb_state", "swarm_id": None}
        result = self.morb_bridge.deploy_morb_swarm(task_type, predicate, target_nodes, parameters)
        return result

    def get_morb_status(self) -> Dict[str, Any]:
        """Public API: Get current MORB deployment status."""
        return self.morb_bridge.get_morb_status()

    # ── MESH TRAVERSAL API ───────────────────────────────────────────────────

    def discover_mesh_nodes(self, force_rescan: bool = False) -> List[Dict[str, Any]]:
        """Public API: Discover all nodes in the substrate mesh."""
        if not self.orb_state.get("mesh_traversal_enabled", False):
            return []
        nodes = self.mesh_traverser.discover_nodes(force_rescan=force_rescan)
        return [
            {
                "node_id": n.node_id,
                "node_type": n.node_type,
                "address": n.address,
                "health_status": n.health_status,
                "last_seen": n.last_seen.isoformat(),
                "capabilities": n.capabilities,
                "load_factor": n.load_factor,
            }
            for n in nodes
        ]

    def probe_mesh_node(self, node_id: str) -> Dict[str, Any]:
        """Public API: Deep health probe of a mesh node."""
        return self.mesh_traverser.probe_node_health(node_id)

    def get_mesh_topology(self) -> Dict[str, Any]:
        """Public API: Get current mesh topology."""
        return self.mesh_traverser.get_mesh_topology()

    def route_mesh_task(self, task_payload: Dict[str, Any], target_node: str) -> Dict[str, Any]:
        """Public API: Route a task to a mesh node."""
        return self.mesh_traverser.route_task(task_payload, target_node)

    # ── DIAGNOSTIC API ────────────────────────────────────────────────────────

    def run_diagnostics(self) -> Dict[str, Any]:
        """Public API: Run full system diagnostics."""
        return self.diagnostic_system.full_system_probe()

    def get_diagnostic_history(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Public API: Get recent diagnostic runs."""
        return self.diagnostic_system.get_probe_history(limit=limit)

    # ── LEARNING API ──────────────────────────────────────────────────────────

    def run_learning_prune(self) -> Dict[str, Any]:
        """Public API: Aggressively prune stale patterns."""
        return self.learning_loop.run_aggressive_prune()

    def get_learning_stats(self) -> Dict[str, Any]:
        """Public API: Get aggressive learning statistics."""
        return self.learning_loop.get_learning_stats()

    # ── VOICE ────────────────────────────────────────────────────────────────

    def speak(self, text: str, emotion: str = "thoughtful_warm") -> Dict[str, Any]:
        settings = dict(self.voice_config)
        emotion_profiles = {
            "thoughtful_warm": {"speed": 0.95, "pitch": 0.1, "emotion": "warm_contemplative"},
            "analytical": {"speed": 0.9, "pitch": 0.0, "emotion": "precise_clear"},
            "uncertain": {"speed": 0.85, "pitch": -0.05, "emotion": "hesitant_exploring"},
            "confident": {"speed": 1.0, "pitch": 0.15, "emotion": "assured_measured"},
        }

        if emotion in emotion_profiles:
            settings.update(emotion_profiles[emotion])

        output_path = self.cali_root / "voice_cache" / f"{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
        synthesis_package = {
            "text": text,
            "voice_config": settings,
            "output_path": str(output_path),
            "gpu_accelerated": str(self.device) == "cuda",
            "timestamp": datetime.now().isoformat(),
            "primary_modality": "voice",
            "fallback_modality": "text",
        }

        meta_path = output_path.with_suffix(".json")
        meta_path.write_text(json.dumps(synthesis_package, indent=2), encoding="utf-8")
        return synthesis_package

    def _background_prefetch(self) -> None:
        try:
            count = self.bulk_mirror.prefetch_all()
            logger.info("Bulk mirror prefetch complete: %d endpoints seeded", count)
        except Exception as exc:
            logger.warning("Bulk mirror prefetch failed: %s", exc)

    def _load_substrate_domain_knowledge(self) -> List[Dict[str, Any]]:
        entries: List[Dict[str, Any]] = []
        if not self.SUBSTRATE_ROOT.exists():
            logger.warning("SUBSTRATE_ROOT not found: %s", self.SUBSTRATE_ROOT)
            return entries

        for csv_path in self.SUBSTRATE_ROOT.rglob("*.csv"):
            try:
                with csv_path.open(newline="", encoding="utf-8") as fh:
                    reader = csv.DictReader(fh)
                    for row in reader:
                        content = self._csv_row_to_content(row, csv_path)
                        if not content:
                            continue
                        entries.append({
                            "type": "substrate_domain_knowledge",
                            "source": str(csv_path.relative_to(self.SUBSTRATE_ROOT)),
                            "domain": csv_path.parent.name,
                            "content": content,
                            "row_id": row.get("id") or row.get("name") or "",
                        })
            except Exception as exc:
                logger.warning("Failed to load substrate CSV %s: %s", csv_path, exc)

        logger.info("Substrate domain knowledge loaded: %d entries from %s", len(entries), self.SUBSTRATE_ROOT)
        return entries

    @staticmethod
    def _csv_row_to_content(row: Dict[str, Any], csv_path: Path) -> str:
        priority = [
            row.get("name") or "",
            row.get("description") or "",
            row.get("keywords") or "",
            row.get("semantic_tags") or "",
            row.get("category") or "",
            row.get("implications") or "",
            row.get("implications_for_assets") or "",
            row.get("edge_case_handling") or "",
            row.get("example_metric_or_standard") or "",
            row.get("cross_domain_links") or "",
        ]
        parts = [p.replace(",", " ").strip() for p in priority if p.strip()]
        return " | ".join(parts) if parts else ""

    def _inject_substrate_knowledge(self) -> None:
        entries = self._load_substrate_domain_knowledge()
        if not entries:
            return

        self.a_priori_vault["entries"].extend(entries)

        for entry in entries:
            node_id = f"substrate_{entry['row_id'] or hash(entry['content'])}"
            self.kg.add_node(
                node_id,
                type="substrate_domain_knowledge",
                domain=entry.get("domain", "unknown"),
                source=entry.get("source", ""),
            )
            self.kg.add_edge("cali_identity", node_id, weight=0.6, relation="domain_knowledge")
            self.kg.add_edge("vault_a_priori", node_id, weight=0.8, relation="seeded_from")

        logger.info("Injected %d substrate entries into a_priori vault and KG (%d nodes total)",
                    len(entries), self.kg.number_of_nodes())

    def _load_cognitive_seed_vaults(self) -> None:
        if not self.COGNITIVE_SEED_ROOT.exists():
            logger.debug("Cognitive seed root not found (%s) — skipping", self.COGNITIVE_SEED_ROOT)
            return

        vault_files = sorted(self.COGNITIVE_SEED_ROOT.glob("*_vault.json"))
        if not vault_files:
            logger.debug("No cognitive seed vaults found in %s", self.COGNITIVE_SEED_ROOT)
            return

        total_entries = 0
        for vault_file in vault_files:
            try:
                vault_data = json.loads(vault_file.read_text(encoding="utf-8"))
            except Exception as exc:
                logger.warning("Failed to read cognitive vault %s: %s", vault_file.name, exc)
                continue

            category = vault_data.get("category", vault_file.stem.replace("_vault", ""))
            sem_tags = vault_data.get("semantic_tags", category)
            source_id = f"cognitive_seed_{category}"

            for conv in vault_data.get("conversations", []):
                relevance = conv.get("relevance_score", 0)
                for seg_idx, segment in enumerate(conv.get("segments", [])):
                    text = segment.get("text", "").strip()
                    if not text:
                        continue

                    density = segment.get("density_score", 0)
                    row_id = f"cog_{category[:8]}_{abs(hash(text)) % 0xFFFFF:05x}_{seg_idx}"

                    entry = {
                        "type": "cognitive_seed",
                        "source": str(vault_file.relative_to(self.COGNITIVE_SEED_ROOT)),
                        "domain": "cognitive_layer",
                        "cognitive_category": category,
                        "semantic_tags": sem_tags,
                        "content": text,
                        "row_id": row_id,
                        "relevance_score": relevance,
                        "density_score": density,
                        "conversation_title": conv.get("title", ""),
                    }
                    self.a_priori_vault["entries"].append(entry)

                    node_weight = 0.85 if density >= 4 else 0.65
                    self.kg.add_node(
                        row_id,
                        type="cognitive_seed",
                        domain="cognitive_layer",
                        category=category,
                        source=source_id,
                    )
                    self.kg.add_edge("cali_identity", row_id, weight=node_weight, relation="cognitive_layer")
                    self.kg.add_edge("vault_a_priori", row_id, weight=0.80, relation="seeded_from")
                    total_entries += 1

        logger.info("Cognitive seed vaults loaded: %d segments from %d files into a_priori vault",
                    total_entries, len(vault_files))

    def self_prune(self) -> Dict[str, Any]:
        cutoff = (datetime.now() - timedelta(days=30)).isoformat()
        with self.db_lock:
            cursor = self.patterns_db.cursor()
            cursor.execute(
                "DELETE FROM patterns WHERE timestamp < ? AND confidence < 0.3",
                (cutoff,),
            )
            removed = cursor.rowcount
            self.patterns_db.commit()
            cursor.execute("VACUUM")
            self.patterns_db.commit()

        orphaned = [node for node in self.kg.nodes() if self.kg.in_degree(node) == 0 and node != "cali_identity"]
        for node in orphaned:
            self.kg.add_edge("cali_identity", node, weight=0.3, relation="repaired_connection")

        logger.info("Self-pruning complete. Removed %s stale patterns.", removed)
        return {
            "removed_patterns": removed,
            "repaired_nodes": orphaned,
            "timestamp": datetime.now().isoformat(),
        }

    def set_orb_state(self, setting: str, value: Any) -> bool:
        if setting not in self.orb_state:
            return False
        self.orb_state[setting] = value
        logger.info("Orb state updated: %s = %s", setting, value)
        return True

    def get_status(self) -> Dict[str, Any]:
        try:
            from audio_runtime import AudioRuntime
        except ImportError:
            AudioRuntime = None
        try:
            from voice_engine_manager import get_voice_manager
        except ImportError:
            get_voice_manager = None

        audio_status = None
        if hasattr(self, 'audio_runtime') and self.audio_runtime:
            try:
                audio_status = self.audio_runtime.get_status()
            except Exception as exc:
                audio_status = {"error": str(exc)}
        elif AudioRuntime:
            try:
                audio_runtime = AudioRuntime(str(self.cali_root))
                audio_status = audio_runtime.get_status()
            except Exception as exc:
                audio_status = {"error": str(exc)}
        else:
            audio_status = {"error": "audio_runtime unavailable"}

        voice_status = None
        if get_voice_manager:
            try:
                voice_status = get_voice_manager().get_status()
            except Exception as exc:
                voice_status = {"error": str(exc)}
        else:
            voice_status = {"error": "voice_engine_manager unavailable"}

        llm_status = {
            "connected": False,
            "ready": False,
            "model": str(self.orb_state.get("llm_local_model") or os.getenv("ORB_LOCAL_LLM_MODEL", "llama3.2:1b")).strip() or "llama3.2:1b",
            "endpoint": str(self.orb_state.get("llm_local_endpoint") or os.getenv("ORB_LOCAL_LLM_ENDPOINT", "http://127.0.0.1:11434")).strip() or "http://127.0.0.1:11434",
            "available_models": [],
            "status_code": 0,
            "error": "not_checked",
        }
        try:
            from llm_client import _probe_local_llm_health
            llm_status = _probe_local_llm_health(
                endpoint=self.orb_state.get("llm_local_endpoint"),
                model=self.orb_state.get("llm_local_model"),
            )
            llm_status["connected"] = bool(llm_status.get("connected", llm_status.get("ready")))
        except Exception as exc:
            llm_status["error"] = str(exc)
            llm_status["connected"] = False
            llm_status["ready"] = False

        # ── NEW: v3.5 status additions ──────────────────────────────────────
        morb_status = self.morb_bridge.get_morb_status() if hasattr(self, 'morb_bridge') and self.morb_bridge else {"error": "not_initialized"}
        mesh_status = self.mesh_traverser.get_mesh_topology() if hasattr(self, 'mesh_traverser') and self.mesh_traverser else {"error": "not_initialized"}
        learning_stats = self.learning_loop.get_learning_stats() if hasattr(self, 'learning_loop') and self.learning_loop else {"error": "not_initialized"}
        diagnostic_summary = self.diagnostic_system.probe_history[-1] if hasattr(self, 'diagnostic_system') and self.diagnostic_system.probe_history else {"error": "no_history"}

        return {
            "identity": "CALI - Cognitively Aligned Linear Intelligence",
            "instance_id": self.instance_id,
            "version": "3.5.0",
            "device": str(self.device),
            "vram_gb": self.vram_gb,
            "system_path": str(self.system_path),
            "cali_root": str(self.cali_root),
            "shared_mesh_root": self.shared_mesh_root,
            "partition_bytes": self.partition_size,
            "philosophical_seeds": list(self.PHILOSOPHER_SEEDS.keys()),
            "a_priori_entries": len(self.a_priori_vault["entries"]),
            "a_posteriori_entries": len(self.a_posteriori_vault["entries"]),
            "knowledge_graph_nodes": self.kg.number_of_nodes(),
            "knowledge_graph_edges": self.kg.number_of_edges(),
            "interaction_count": self.interaction_count,
            "orb_state": self.orb_state,
            "voice_primary": True,
            "acp_active": True,
            "swarm_ready": True,
            "encoder_backend": self.encoder_backend,
            "audio_runtime": audio_status,
            "voice_engine_manager": voice_status,
            "llm_status": llm_status,
            # v3.5 additions
            "morb_status": morb_status,
            "mesh_status": mesh_status,
            "learning_stats": learning_stats,
            "last_diagnostic": diagnostic_summary,
        }

    async def aclose(self) -> None:
        # Stop learning loop
        if hasattr(self, 'learning_loop') and self.learning_loop:
            self.learning_loop.stop_background_learning()

        try:
            if self.swarm.session is not None or self.swarm._workers:
                await self.swarm.close()
        except Exception as exc:
            logger.warning("Failed to close swarm session cleanly: %s", exc)

        with self.db_lock:
            if self.patterns_db:
                self.patterns_db.close()
                self.patterns_db = None

    def close(self) -> None:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(self.aclose())
            return

        loop.create_task(self.aclose())

    @staticmethod
    def _score_text_match(query: str, content: str) -> float:
        query_tokens = {token for token in query.lower().split() if token}
        content_tokens = {token for token in content.lower().split() if token}
        if not query_tokens or not content_tokens:
            return 0.0
        overlap = query_tokens & content_tokens
        if not overlap:
            return 0.0
        return len(overlap) / len(query_tokens | content_tokens)

    @staticmethod
    def _cosine_similarity(left: np.ndarray, right: np.ndarray) -> float:
        left_norm = float(np.linalg.norm(left))
        right_norm = float(np.linalg.norm(right))
        if left_norm == 0 or right_norm == 0:
            return 0.0
        return float(np.dot(left, right) / (left_norm * right_norm))


__all__ = ["CALISKG", "MORBDeploymentBridge", "SubstrateMeshTraverser",
           "DiagnosticProbeSystem", "AggressiveLearningLoop", "MORBTask",
           "MeshNode", "DiagnosticReport", "LearnedPattern", "SwarmTask"]
