#!/usr/bin/env python3
"""CALI SKG v3.0 cognitive subsystem for Orb Assistant."""

from __future__ import annotations

import asyncio
import csv
import hashlib
import json
import logging
import os
import pickle
import sqlite3
import threading
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum, auto
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

import numpy as np


def r_drive_path(*parts: str) -> Path:
    """Resolve R-drive substrate paths deterministically for Windows and WSL."""
    root = os.getenv("ORB_R_DRIVE_ROOT")
    if not root:
        root = "/mnt/r" if os.name != "nt" else "R:/"
    return Path(root).joinpath(*parts)


# Optional dependencies with graceful degradation
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


class BulkMirrorCache:
    """
    Local disk mirror for API research results.

    Each API defined in research_api_manifest.json has a `storage_hint` pointing to
    R:\\datasets\\bulk_mirrors\\{category}\\. This class:
      - Writes swarm results there on every successful fetch (filling the empty mirrors).
      - Reads cached results back to avoid redundant network calls.
      - Exposes pre-fetchable (no-auth) endpoints so the mirror can be seeded at startup.
    """

    MANIFEST_PATH = r_drive_path("manifests", "research_api_manifest.json")
    BULK_MIRRORS_ROOT = r_drive_path("datasets", "bulk_mirrors")
    MAX_CACHE_AGE_HOURS = 24         # treat cache stale after 24 h
    MAX_CACHE_FILE_SIZE_BYTES = 2_000_000  # 2 MB cap per file

    def __init__(self) -> None:
        self.manifest: Dict[str, Any] = {}
        self.api_map: Dict[str, Dict[str, Any]] = {}   # api_id → api entry
        self.category_map: Dict[str, str] = {}          # api_id → storage_hint dir
        self._load_manifest()

    # ── manifest loading ───────────────────────────────────────────────────────

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

    # ── write ─────────────────────────────────────────────────────────────────

    def write(self, api_id: str, data: Any, query: str = "") -> Optional[Path]:
        """
        Persist API result data to the correct bulk mirror directory.
        Returns the written file path, or None on failure.
        """
        hint = self.category_map.get(api_id)
        if not hint:
            # Fall back to category field on the api entry
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

    # ── read ──────────────────────────────────────────────────────────────────

    def read_category(self, category: str, max_files: int = 5) -> List[Dict[str, Any]]:
        """
        Return recent cached results for a given category directory name.
        Used by research() to get offline data before hitting the network.
        """
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
        """True if the mirror for this category has at least one file newer than MAX_CACHE_AGE_HOURS."""
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
        """Return a dict of category → recent cached results for all non-empty mirrors."""
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

    # ── pre-fetch (no-auth APIs) ──────────────────────────────────────────────

    def get_prefetchable_apis(self) -> List[Dict[str, Any]]:
        """
        Return API entries that require no authentication — safe to pre-fetch
        at startup to seed the mirrors without needing any API keys.
        """
        return [
            api for api in self.api_map.values()
            if api.get("auth") in ("none", "optional_key", None)
        ]

    def prefetch_all(self) -> int:
        """
        Synchronously pre-fetch all no-auth endpoints and write to bulk mirrors.
        Called at startup to seed empty mirrors. Returns count of successful fetches.
        """
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
                    headers={"User-Agent": "CALI-BulkMirror/3.0"},
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

    # ── summary text (for a_posteriori evidence) ──────────────────────────────

    def summarize_for_query(self, query: str, domains: List[str]) -> List[str]:
        """
        Given a query and list of domain names, scan relevant mirrors and return
        short text snippets suitable for injecting into a_posteriori evidence.
        """
        tokens = set(query.lower().split())
        snippets: List[str] = []

        # Map broad domain names to mirror category folders
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
                # Try direct folder name match
                candidate = self.BULK_MIRRORS_ROOT / slug
                if candidate.exists():
                    categories_to_check.add(slug)

        for category in categories_to_check:
            for cached in self.read_category(category, max_files=3):
                data = cached.get("data", {})
                text = self._extract_text(data)
                if text:
                    # Score relevance
                    text_tokens = set(text.lower().split())
                    if tokens & text_tokens:
                        snippets.append(f"[{category}/{cached.get('api_id', '?')}] {text[:200]}")

        return snippets[:6]

    def weight_api_confidence(self, api_id: str, raw_quality: float) -> tuple:
        """
        Compute weighted (confidence, truth_likelihood) for a single API result.

        Factors:
          priority:   high=0.85  medium=0.70  low=0.55  (manifest field)
          auth:       none / optional_key = ×0.90  (public but unverified)
                      api_key_required    = ×1.00  (provider-authenticated)
          raw_quality: _assess_data_quality() score from the swarm (0–1)

        Final confidence = priority_base × auth_multiplier × raw_quality,
        clamped to [0.35, 0.95].
        Truth likelihood = confidence × 0.90 (slight deflation — empirical data).
        """
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
            # Flatten first-level string values
            parts = [str(v) for v in data.values() if isinstance(v, str) and v.strip()]
            return " ".join(parts[:3])[:400]
        if isinstance(data, list) and data:
            return BulkMirrorCache._extract_text(data[0])
        return ""


class CALISwarmOrchestrator:
    """Parallel API research orchestration."""

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
                headers={"User-Agent": "CALI-Orb-Research/3.0"},
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

        # Write successful results to bulk mirror so they persist for offline retrieval
        if self.bulk_mirror:
            for result in task.results:
                if result.get("error"):
                    continue
                api_name = result.get("api", "")
                # Find api_id by matching name in manifest
                api_id = next(
                    (aid for aid, entry in self.bulk_mirror.api_map.items()
                     if entry.get("name", "") == api_name or aid == api_name),
                    api_name.lower().replace(" ", "_"),
                )
                # Compute real weighted confidence so vault writes carry accurate scores
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
        request = urllib.request.Request(full_url, headers=headers or {"User-Agent": "CALI-Orb-Research/3.0"})
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


class CALISKG:
    """CALI: Cognitively Aligned Linear Intelligence."""

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

    # Path to CALI_SUBSTRATE domain knowledge CSVs
    SUBSTRATE_ROOT = r_drive_path("CALI_SUBSTRATE", "domain_knowledge")
    # Path to cognitive seed vaults produced by cognitive_substrate_extractor.py
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

        # Inject CALI_SUBSTRATE CSV knowledge into a_priori vault and KG
        self._inject_substrate_knowledge()

        # Inject cognitive seed vaults (produced by cognitive_substrate_extractor.py)
        self._load_cognitive_seed_vaults()

        # Seed bulk mirrors from no-auth APIs in a background thread (non-blocking)
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
            "llm_governance_wrapper": os.getenv("ORB_LLM_GOVERNANCE_WRAPPER", "1").strip().lower() in {"1", "true", "yes", "on"},
            "llm_retain_voice": os.getenv("ORB_LLM_RETAIN_VOICE", "1").strip().lower() in {"1", "true", "yes", "on"},
        }

        logger.info("CALI SKG initialized | Device: %s | Partition: %sGB", self.device, partition_size_gb)

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
        """
        Load packaged Core-4 SKG json files into a priori seeds so the desktop orb
        has a real knowledge base when running without UCM.
        """
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

                # Core axiom as a seed entry
                core = payload.get("core_axiom", {})
                if core:
                    entries.append(
                        {
                            "type": "core_axiom",
                            "philosopher": philosopher,
                            "source": path.name,
                            "node_id": core.get("node_id"),
                            "label": core.get("label"),
                            "definition": core.get("definition"),
                            "properties": core.get("properties", {}),
                        }
                    )

                # Concept nodes
                for node in payload.get("concept_nodes", []) or []:
                    entries.append(
                        {
                            "type": "concept",
                            "philosopher": philosopher,
                            "source": path.name,
                            "node_id": node.get("node_id"),
                            "label": node.get("label"),
                            "category": node.get("category"),
                            "definition": node.get("properties", {}).get("definition"),
                            "properties": node.get("properties", {}),
                            "relationships": node.get("relationships", {}),
                        }
                    )

                # Reasoning rules
                for rule in payload.get("reasoning_rules", []) or []:
                    entries.append(
                        {
                            "type": "reasoning_rule",
                            "philosopher": philosopher,
                            "source": path.name,
                            "rule_id": rule.get("rule_id"),
                            "name": rule.get("name"),
                            "priority": rule.get("priority"),
                            "logic": rule.get("logic"),
                            "condition": rule.get("condition"),
                            "action": rule.get("action"),
                        }
                    )

                # Flow templates
                for flow in payload.get("reasoning_flow_templates", []) or []:
                    entries.append(
                        {
                            "type": "reasoning_flow",
                            "philosopher": philosopher,
                            "source": path.name,
                            "template_id": flow.get("template_id") or flow.get("name"),
                            "steps": flow.get("steps", []),
                        }
                    )

                # Taxonomies
                taxonomies = payload.get("hierarchical_taxonomies")
                if isinstance(taxonomies, list):
                    for tax in taxonomies:
                        entries.append(
                            {
                                "type": "taxonomy",
                                "philosopher": philosopher,
                                "source": path.name,
                                "name": tax.get("name"),
                                "levels": tax.get("levels"),
                            }
                        )
                elif isinstance(taxonomies, dict):
                    for name, body in taxonomies.items():
                        entries.append(
                            {
                                "type": "taxonomy",
                                "philosopher": philosopher,
                                "source": path.name,
                                "name": name,
                                "levels": body,
                            }
                        )
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

        for node in (
            "vault_a_priori",
            "vault_a_posteriori",
            "acp_cochlea",
            "softmax_advisory",
            "swarm_orchestrator",
            "voice_synthesis",
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

        return {
            "query": query,
            "philosophical_reasoning": reasoning_outputs,
            "advisory_verdict": advisory,
            "recommended_response": response_text,
            "voice_ready": True,
            "timestamp": datetime.now().isoformat(),
        }

    def _apply_philosophical_logic(
        self,
        query: str,
        seed: PhilosophicalSeed,
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
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

    def _retrieve_vault_matches(
        self,
        entries: List[Dict[str, Any]],
        query: str,
        limit: int,
    ) -> List[str]:
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

    def _remember_pattern(
        self,
        content: str,
        reasoning_mode: ReasoningMode,
        confidence: float,
        truth_likelihood: float,
        source: str,
    ) -> None:
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

    def _store_research_return(
        self,
        query: str,
        synthesis: Dict[str, Any],
        raw_results: List[Dict[str, Any]],
    ) -> None:
        """Write a research return to both vaults with real confidence weighting.

        A_posteriori: one entry per research call (empirical, LOCKE_EMPIRICAL).
        A_priori (in-memory only): crystallize findings whose confidence ≥ 0.82.
        Patterns DB: query→findings for future inductive recall.

        Confidence is derived from per-API weighted_confidence values stamped by
        the swarm (priority × auth × raw_quality).  Falls back to the synthesis
        aggregate when individual weights are unavailable.
        """
        # ── Aggregate per-API weighted confidences ────────────────────────────
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

        # ── Summarise findings for vault content ──────────────────────────────
        findings = synthesis.get("key_findings") or []
        finding_text = "; ".join(str(f) for f in findings[:3]) if findings else "(no findings)"

        # ── A_posteriori vault write ──────────────────────────────────────────
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
            "content": (
                f"Research: {query} | Findings: {finding_text} | Confidence: {confidence:.3f}"
            ),
        }
        self.a_posteriori_vault["entries"].append(entry)
        with self.a_posteriori_vault["path"].open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry) + "\n")

        # ── Pattern memory (Locke: API results are sensory evidence) ─────────
        self._remember_pattern(
            content=f"{query} -> {finding_text}",
            reasoning_mode=ReasoningMode.LOCKE_EMPIRICAL,
            confidence=confidence,
            truth_likelihood=truth_likelihood,
            source="swarm_research",
        )

        # ── Crystallize high-confidence findings into in-memory a_priori ─────
        if confidence >= 0.82 and findings:
            crystallized = {
                "row_id": f"crystal_{hash(query) & 0xFFFFFFFF}",
                "source": "crystallized_research",
                "content": f"[Research:{confidence:.2f}] {finding_text}",
                "domain": (synthesis.get("domains") or ["general"])[0],
                "timestamp": datetime.now().isoformat(),
            }
            self.a_priori_vault["entries"].append(crystallized)
            logger.info(
                "Crystallized high-confidence research (%.3f) into a_priori vault: %s",
                confidence, query[:60],
            )

    def _resolve_top_reasoning_mode(
        self,
        advisory: Dict[str, Any],
        reasoning: List[Dict[str, Any]],
    ) -> ReasoningMode:
        weights = advisory.get("weights") or []
        if not weights:
            return ReasoningMode.KANT_SYNTHETIC

        top_index = int(np.argmax(weights))
        top_logic = reasoning[top_index].get("logic_type", ReasoningMode.KANT_SYNTHETIC.name)
        return ReasoningMode[top_logic]

    def _formulate_response(
        self,
        query: str,
        advisory: Dict[str, Any],
        reasoning: List[Dict[str, Any]],
    ) -> str:
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

        # ── Bulk mirror check — serve cached data before hitting the network ──
        mirror_snippets = self.bulk_mirror.summarize_for_query(query, selected_domains)
        if mirror_snippets:
            logger.info(
                "BulkMirror cache hit for query '%s': %d snippets from local mirror",
                query[:50], len(mirror_snippets),
            )

        await self.swarm.initialize()
        self.set_orb_state("swarm_visible", True)
        task_id = await self.swarm.spawn_research_orbs(query, selected_domains)
        synthesis = await self.swarm.ingest_results(task_id)

        # Merge any mirror snippets into synthesis key_findings
        if mirror_snippets:
            existing = synthesis.get("key_findings") or []
            synthesis["key_findings"] = (
                [f"[CACHED] {s}" for s in mirror_snippets[:2]] + existing
            )
            synthesis["bulk_mirror_hits"] = len(mirror_snippets)

        # Retrieve per-API results from swarm task for confidence weighting
        swarm_task = self.swarm.active_tasks.get(task_id)
        raw_results = swarm_task.results if swarm_task else []

        # Write to both vaults with real weighted confidence (not hardcoded values)
        synthesis["domains"] = selected_domains
        self._store_research_return(query, synthesis, raw_results)

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
        """
        Runs in a daemon thread at startup.
        Pre-fetches all no-auth API endpoints and writes them to bulk_mirrors,
        so the system has local cached data available for offline retrieval.
        """
        try:
            count = self.bulk_mirror.prefetch_all()
            logger.info("Bulk mirror prefetch complete: %d endpoints seeded", count)
        except Exception as exc:
            logger.warning("Bulk mirror prefetch failed: %s", exc)

    def _load_substrate_domain_knowledge(self) -> List[Dict[str, Any]]:
        """
        Scan CALI_SUBSTRATE/domain_knowledge for CSV files and convert each row
        into a structured a_priori entry so the knowledge surfaces during reasoning.
        """
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

        logger.info(
            "Substrate domain knowledge loaded: %d entries from %s",
            len(entries),
            self.SUBSTRATE_ROOT,
        )
        return entries

    @staticmethod
    def _csv_row_to_content(row: Dict[str, Any], csv_path: Path) -> str:
        """
        Convert a CSV row into a flat natural-language content string that the
        vault matcher can score against free-text queries.
        """
        # Priority fields that carry the most semantic weight
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
        """
        Merge substrate CSV entries into the in-memory a_priori vault and add
        each one as a node in the knowledge graph so it participates in reasoning.
        """
        entries = self._load_substrate_domain_knowledge()
        if not entries:
            return

        # Extend the in-memory vault (not persisted — re-loaded fresh each boot)
        self.a_priori_vault["entries"].extend(entries)

        # Register each entry as a KG node linked to cali_identity
        for entry in entries:
            node_id = f"substrate_{entry['row_id'] or hash(entry['content'])}"
            self.kg.add_node(
                node_id,
                type="substrate_domain_knowledge",
                domain=entry.get("domain", "unknown"),
                source=entry.get("source", ""),
            )
            self.kg.add_edge(
                "cali_identity",
                node_id,
                weight=0.6,
                relation="domain_knowledge",
            )
            self.kg.add_edge(
                "vault_a_priori",
                node_id,
                weight=0.8,
                relation="seeded_from",
            )

        logger.info(
            "Injected %d substrate entries into a_priori vault and KG (%d nodes total)",
            len(entries),
            self.kg.number_of_nodes(),
        )

    def _load_cognitive_seed_vaults(self) -> None:
        """
        Load cognitive seed vault JSONs produced by cognitive_substrate_extractor.py
        and inject each high-relevance segment into the in-memory a_priori vault
        and knowledge graph.

        Vault files live at:
          R:\\CALI_SUBSTRATE\\seeds\\cognitive_seed_vault\\{category}_vault.json

        Each conversation's segments become individual a_priori entries of type
        'cognitive_seed', linked in the KG to 'cali_identity' with relation
        'cognitive_layer'.  High-density segments (density_score ≥ 4) get an
        elevated KG edge weight of 0.85 vs the default 0.65.

        Run tools\\cognitive_substrate_extractor.py to (re)generate the vaults.
        If the seeds directory does not exist or is empty CALI boots normally —
        the cognitive layer is additive, not required.
        """
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

            category  = vault_data.get("category", vault_file.stem.replace("_vault", ""))
            sem_tags  = vault_data.get("semantic_tags", category)
            source_id = f"cognitive_seed_{category}"

            for conv in vault_data.get("conversations", []):
                relevance = conv.get("relevance_score", 0)
                for seg_idx, segment in enumerate(conv.get("segments", [])):
                    text = segment.get("text", "").strip()
                    if not text:
                        continue

                    density = segment.get("density_score", 0)
                    row_id  = (
                        f"cog_{category[:8]}_{abs(hash(text)) % 0xFFFFF:05x}_{seg_idx}"
                    )

                    entry = {
                        "type":               "cognitive_seed",
                        "source":             str(vault_file.relative_to(self.COGNITIVE_SEED_ROOT)),
                        "domain":             "cognitive_layer",
                        "cognitive_category": category,
                        "semantic_tags":      sem_tags,
                        "content":            text,
                        "row_id":             row_id,
                        "relevance_score":    relevance,
                        "density_score":      density,
                        "conversation_title": conv.get("title", ""),
                    }
                    self.a_priori_vault["entries"].append(entry)

                    # KG node — higher-density segments get stronger edge weight
                    node_weight = 0.85 if density >= 4 else 0.65
                    self.kg.add_node(
                        row_id,
                        type="cognitive_seed",
                        domain="cognitive_layer",
                        category=category,
                        source=source_id,
                    )
                    self.kg.add_edge(
                        "cali_identity",
                        row_id,
                        weight=node_weight,
                        relation="cognitive_layer",
                    )
                    self.kg.add_edge(
                        "vault_a_priori",
                        row_id,
                        weight=0.80,
                        relation="seeded_from",
                    )
                    total_entries += 1

        logger.info(
            "Cognitive seed vaults loaded: %d segments from %d files into a_priori vault",
            total_entries, len(vault_files),
        )

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
        # Import here to avoid circular import issues
        try:
            from audio_runtime import AudioRuntime
        except ImportError:
            AudioRuntime = None
        try:
            from voice_engine_manager import get_voice_manager
        except ImportError:
            get_voice_manager = None

        # Audio runtime status
        audio_status = None
        if hasattr(self, 'audio_runtime') and self.audio_runtime:
            try:
                audio_status = self.audio_runtime.get_status()
            except Exception as exc:
                audio_status = {"error": str(exc)}
        elif AudioRuntime:
            try:
                # Try to instantiate with project_root if available
                audio_runtime = AudioRuntime(str(self.cali_root))
                audio_status = audio_runtime.get_status()
            except Exception as exc:
                audio_status = {"error": str(exc)}
        else:
            audio_status = {"error": "audio_runtime unavailable"}

        # Voice engine manager status
        voice_status = None
        if get_voice_manager:
            try:
                voice_status = get_voice_manager().get_status()
            except Exception as exc:
                voice_status = {"error": str(exc)}
        else:
            voice_status = {"error": "voice_engine_manager unavailable"}

        # LLM health check via Ollama /api/tags with deterministic model requirement.
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

        return {
            "identity": "CALI - Cognitively Aligned Linear Intelligence",
            "instance_id": self.instance_id,
            "version": "3.0.0",
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
        }

    async def aclose(self) -> None:
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
