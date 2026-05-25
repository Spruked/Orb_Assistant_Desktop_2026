# Standard library imports
import csv
import hashlib
import json
import math
import os
import sys
import time
from collections import deque
from pathlib import Path

# Third-party imports
from hlsf_geometry.engine import hlsf_singleton

# Local imports
from components.core_4_minds.tribunal import FourMindTribunal
from vault_system.manager import VaultManager

# Conditional imports and path setup
def _setup_project_paths():
    """Set up project paths for component discovery."""
    parent_dir = Path(__file__).resolve().parent.parent
    if str(parent_dir) not in sys.path:
        sys.path.append(str(parent_dir))

    return parent_dir

def _setup_bayesian_engine():
    """Import BayesianEngine with proper path setup."""
    try:
        from bayesian_engine import BayesianEngine
        return BayesianEngine
    except ImportError:
        print("⚠️ BayesianEngine not available", file=sys.stderr)
        return None


def _is_truthy(value: str) -> bool:
    return value.strip().lower() in {"1", "true", "yes", "on"}

def _find_epistemic_gravity_field_path() -> Path:
    """Resolve Epistemic Gravity Field path with deterministic precedence."""
    root_dir = Path(__file__).resolve().parents[2]  # .../Orb_Assistant_Desktop
    env_root = os.getenv("ORB_EGF_ROOT", "").strip()

    search_paths = []
    if env_root:
        search_paths.append(Path(env_root))

    search_paths.extend(
        [
            root_dir / "modules" / "Epistemic_Gravity_Field",
            root_dir / "electron" / "src" / "Epistemic_Gravity_Field",
            Path.cwd() / "modules" / "Epistemic_Gravity_Field",
            Path.cwd() / "Epistemic_Gravity_Field",
        ]
    )

    for path in search_paths:
        if (path / "space_field.py").exists():
            return path

    return root_dir / "modules" / "Epistemic_Gravity_Field"

def _setup_epistemic_gravity_field():
    """Set up Epistemic Gravity Field if enabled and available."""
    if not _is_truthy(os.getenv("ORB_ENABLE_EGF_TENSOR", "0")):
        return None, False

    try:
        egf_path = _find_epistemic_gravity_field_path()
        if not (egf_path / "space_field.py").exists():
            raise ImportError(f"space_field.py not found in {egf_path}")

        if str(egf_path) not in sys.path:
            sys.path.append(str(egf_path))

        from space_field import SpaceFieldCognition
        import torch

        print(f"✓ EGF source wired: {egf_path / 'space_field.py'}", file=sys.stderr)

        return SpaceFieldCognition, True
    except ImportError as e:
        print(f"⚠️ Epistemic Gravity Field not loaded: {e}", file=sys.stderr)
        return None, False

# Initialize paths and components
PROJECT_PARENT = _setup_project_paths()
BayesianEngine = _setup_bayesian_engine()
SpaceFieldCognition, TORCH_AVAILABLE = _setup_epistemic_gravity_field()

CALISKG = None  # Will be set later


class EpistemicGravityBridge:
    """Bridge for Epistemic Gravity Field tensor processing."""

    def __init__(self):
        self.active = TORCH_AVAILABLE and SpaceFieldCognition is not None
        self.field = None
        self.dim = 32  # Default dimension
        self.last_error = None

        if self.active:
            try:
                print("🔗 Initializing Epistemic Gravity Field...", file=sys.stderr)
                self.field = SpaceFieldCognition(device="cpu")
                self.dim = self.field.config.DIM
                print(f"✓ Epistemic Gravity Field online ({self.dim}³ tensor)", file=sys.stderr)
            except Exception as e:
                print(f"❌ Epistemic Gravity Field initialization failed: {e}", file=sys.stderr)
                self.active = False
                self.last_error = str(e)
        else:
            print("ℹ️ Epistemic Gravity Field disabled or unavailable", file=sys.stderr)

    def process_stimulus(self, stimulus):
        """Process stimulus through the epistemic gravity field."""
        if not self.active or not self.field:
            return {}

        try:
            self.field.step()

            if stimulus.get("type") == "cursor_movement":
                coords = stimulus.get("coordinates", [0, 0])

                # Map screen coordinates to tensor dimensions
                x = int((coords[0] / 1920.0) * (self.dim - 1))
                y = int((coords[1] / 1080.0) * (self.dim - 1))
                x = max(0, min(x, self.dim - 1))
                y = max(0, min(y, self.dim - 1))

                # Create and inject signal tensor
                import torch
                signal = torch.zeros(self.dim, self.dim, self.dim, 4)
                z = self.dim // 2  # Inject at center z-plane

                # Calculate intensity based on velocity
                intensity = min(stimulus.get("velocity", 1.0) / 10.0, 1.0)
                signal[x, y, z, :] = intensity

                self.field.broadcast_to_field(signal)

            return self.field.get_field_stats()

        except Exception as e:
            print(f"⚠️ Epistemic Gravity Field processing error: {e}", file=sys.stderr)
            self.last_error = str(e)
            return {}

    def get_visual_state(self, stats=None):
        """Return a compact renderer-facing telemetry packet for inner-orb visuals."""
        if not self.active or not self.field:
            return {
                "type": "egf_state",
                "ok": False,
                "mode": "unavailable",
                "error": self.last_error or "egf_unavailable",
            }

        stats = stats if isinstance(stats, dict) else self.field.get_field_stats()
        if not stats:
            return {
                "type": "egf_state",
                "ok": False,
                "mode": "fault",
                "error": self.last_error or "get_field_stats returned empty dict",
            }

        center = float(stats.get("center_entropy", 0.0) or 0.0)
        middle = float(stats.get("middle_entropy", 0.0) or 0.0)
        outer = float(stats.get("outer_entropy", 0.0) or 0.0)
        pressure = float(stats.get("renewal_pressure", 0.0) or 0.0)

        try:
            activation_peak = float(torch.max(torch.abs(self.field.cubes.activation)).item())
        except Exception:
            activation_peak = 0.0

        imbalance = abs(center - outer)
        if pressure > 0.45:
            mode = "pressure"
        elif imbalance < 0.05 and pressure < 0.2:
            mode = "stable"
        elif outer > center:
            mode = "turbulent"
        else:
            mode = "active"

        return {
            "type": "egf_state",
            "ok": True,
            "step_count": int(getattr(self.field, "step_count", 0)),
            "center_entropy": round(center, 6),
            "middle_entropy": round(middle, 6),
            "outer_entropy": round(outer, 6),
            "renewal_pressure": round(pressure, 6),
            "activation_peak": round(activation_peak, 6),
            "field_imbalance": round(imbalance, 6),
            "mode": mode,
        }


# --------------------------------


class CrossDomainPredicate:
    """Emergent thought-object synthesized across epistemic, spatial, and logic domains."""

    def __init__(self, epistemic, spatial, logic, synthesis_confidence):
        self.epistemic_traces = epistemic
        self.hlsf_node = spatial
        self.logic_validity = logic
        self.confidence = synthesis_confidence
        self.timestamp = time.time()

    def pulse(self):
        mode = self.logic_validity.get("active_mode") or (
            "INTUITION-JUMP"
            if self.logic_validity.get("intuitive_jump_triggered")
            else "HABIT" if self.logic_validity.get("custom_habit_active") else "GUARD"
        )
        result = {
            "glow_intensity": self.confidence,
            "cognitive_mode": mode,
            "spatial_coordinate": self.hlsf_node,
            "epistemic_alignment": self._calculate_axiomatic_alignment(),
            "deterministic": self.confidence > 0.95,
            "predictive_intent": self.logic_validity.get("inductive_prediction", {}),
            "jump_vector": self.logic_validity.get("necessity_vector", []),
            "navigation_vector": getattr(self, "navigation_vector", None),
            "final_verdict": getattr(self, "final_verdict", None),
            "final_verdict_source": getattr(self, "final_verdict_source", None),
        }
        return {k: v for k, v in result.items() if v is not None}

    def internal_state(self):
        return {
            "ucm_envelope": getattr(self, "ucm_envelope", None),
            "cali_reflection": getattr(self, "cali_reflection", None),
        }

    def _calculate_axiomatic_alignment(self):
        if not self.epistemic_traces:
            return 0.0
        confidences = [
            trace.get("confidence", 0.5) for trace in self.epistemic_traces.values()
        ]
        return sum(confidences) / len(confidences)


class HabitTracker:
    """Humean constant conjunction tracker for cursor movements."""

    def __init__(self, vault_manager):
        self.vault = vault_manager
        if not hasattr(self.vault, "posteriori_cache"):
            self.vault.posteriori_cache = {}
        self.sequence_buffer = deque(maxlen=5)
        self.pattern_cache = {}

    def record_observation(self, stimulus):
        if stimulus.get("type") != "cursor_movement":
            return None
        coords = stimulus.get("coordinates", [0, 0])
        quadrant = self._coords_to_quadrant(coords)
        observation = {
            "quadrant": quadrant,
            "coords": coords,
            "velocity": stimulus.get("velocity", 0.0),
            "timestamp": time.time(),
        }
        self.sequence_buffer.append(observation)
        if len(self.sequence_buffer) >= 3:
            pattern_key = self._serialize_pattern(list(self.sequence_buffer))
            self._update_conjunction_frequency(pattern_key)
        return observation

    def predict_next(self):
        if len(self.sequence_buffer) < 3:
            return None
        current_pattern = self._serialize_pattern(list(self.sequence_buffer)[-3:])
        cached = getattr(self.vault, "posteriori_cache", {}).get(
            f"habit_{current_pattern}"
        )
        if cached:
            return {
                "prediction_type": "QUADRANT_TRANSITION",
                "target": cached.get("predicted_next"),
                "confidence": cached.get("frequency", 0.0),
                "hume_vivacity": min(cached.get("frequency", 0) * 1.2, 1.0),
            }
        return {"prediction_type": "UNSURE", "confidence": 0.3, "hume_vivacity": 0.4}

    def _coords_to_quadrant(self, coords):
        x, y = coords[0], coords[1]
        grid_x = 1920 / 2
        grid_y = 1080 / 2
        col = 0 if x < grid_x else 1
        row = 0 if y < grid_y else 1
        return ["NW", "NE", "SW", "SE"][row * 2 + col]

    def _serialize_pattern(self, sequence):
        return "_".join([s["quadrant"] for s in sequence])

    def _update_conjunction_frequency(self, pattern_key):
        if pattern_key not in self.pattern_cache:
            self.pattern_cache[pattern_key] = {"count": 0}
        self.pattern_cache[pattern_key]["count"] += 1
        self.vault.crystallize(
            f"habit_{pattern_key}",
            {
                "pattern": pattern_key,
                "frequency": min(self.pattern_cache[pattern_key]["count"] / 10.0, 1.0),
                "predicted_next": self._extrapolate_next_quadrant(pattern_key),
                "temporal_decay": 0.95,
            },
        )

    def _extrapolate_next_quadrant(self, pattern_key):
        parts = pattern_key.split("_")
        return parts[-1] if len(parts) >= 2 else "UNKNOWN"

    def get_quadrant_heat(self, quadrant_code):
        """Returns rough usage frequency of a quadrant to aid avoidance."""
        heat = 0
        for pattern, data in self.pattern_cache.items():
            if quadrant_code in pattern:
                heat += data.get("count", 0)
        return min(heat / 100.0, 1.0)  # Normalize cap


class SpinozaEngine:
    """Minimal rule executor using the Spinoza SKG seed."""

    def __init__(self, repo_root: Path):
        seed_path = repo_root / "components" / "core_4_minds" / "bspinoza" / "spinoza_monism_skg.json"
        self.seed = {}
        self.rules = []
        self.core_axiom = {}
        if seed_path.exists():
            try:
                payload = json.loads(seed_path.read_text(encoding="utf-8"))
                self.seed = payload
                self.core_axiom = payload.get("core_axiom", {})
                self.rules = payload.get("reasoning_rules", [])
                print(f"✓ Spinoza SKG loaded ({len(self.rules)} rules)", flush=True)
            except Exception as exc:
                print(f"⚠️ Spinoza SKG failed to load: {exc}", flush=True)
        else:
            print(f"⚠️ Spinoza SKG missing at {seed_path}", flush=True)

    def reason(self, query: str) -> dict:
        """Apply a tiny deterministic mapping from query keywords to Spinozan principles."""
        q = (query or "").lower()
        verdict = None
        principle = None
        applied_rules = []
        confidence = 0.55

        def apply(rule_id):
            for r in self.rules:
                if r.get("rule_id") == rule_id:
                    applied_rules.append(r)
                    return

        if any(k in q for k in ("freedom", "choice", "will")):
            verdict = "All actions follow necessity; freedom is understanding necessity."
            principle = "Determinism"
            confidence = 0.72
            apply("SPINOZA_RULE_002")
        elif any(k in q for k in ("body", "mind", "dualism", "interaction")):
            verdict = "Mind and body are parallel attributes of one substance."
            principle = "Parallelism"
            confidence = 0.7
            apply("SPINOZA_RULE_003")
        elif any(k in q for k in ("emotion", "affect", "desire", "fear", "hope")):
            verdict = "Emotions are modes; increase adequate ideas to transform affects."
            principle = "Conatus / Affects"
            confidence = 0.68
            apply("SPINOZA_RULE_004")
        elif any(k in q for k in ("god", "nature", "substance")):
            verdict = "There is one substance—Deus sive Natura; modes express it."
            principle = "Substance Monism"
            confidence = 0.75
            apply("SPINOZA_RULE_001")
        else:
            verdict = "Seek adequate ideas; align with necessity."
            principle = "Adequate Ideas"
            confidence = 0.58
            apply("SPINOZA_RULE_005")

        return {
            "philosopher": "Baruch Spinoza",
            "verdict": verdict,
            "principle": principle,
            "applied_rules": applied_rules,
            "core_axiom": self.core_axiom,
            "confidence": confidence,
            "response_text": verdict,
        }


class IntuitiveRecognizer:
    """Spinozan necessity recognizer for high-density fields."""

    def __init__(self, hlsf_engine):
        self.hlsf = hlsf_engine
        self.symmetry_threshold = 0.9
        self.density_threshold = 50

    def check_necessity(self, stimulus, current_node):
        field_density = len(self.hlsf.field_map)
        if field_density > self.density_threshold:
            symmetry_score = self._calculate_bilateral_symmetry()
            if symmetry_score > self.symmetry_threshold:
                necessity_vector = self._calculate_substance_vector(current_node)
                return {
                    "jump_triggered": True,
                    "necessity_vector": necessity_vector,
                    "substance_unity_score": symmetry_score,
                    "bypass_steps": field_density // 10,
                    "spinozan_certainty": 0.98,
                    "field_density": field_density,
                }
        return {
            "jump_triggered": False,
            "field_density": field_density,
            "spinozan_certainty": 0.0,
            "substance_unity_score": self._calculate_bilateral_symmetry(),
        }

    def _calculate_bilateral_symmetry(self):
        if not self.hlsf.field_map:
            return 0.0
        nodes = list(self.hlsf.field_map.values())
        if len(nodes) < 2:
            return 0.0
        mirror_count = 0
        coords_list = [n.coordinates for n in nodes]
        for i, c1 in enumerate(coords_list):
            for c2 in coords_list[i + 1 :]:
                if len(c1) >= 2 and len(c2) >= 2:
                    if abs(c1[0] + c2[0]) < 0.2 and abs(c1[1] - c2[1]) < 0.2:
                        mirror_count += 1
        total_pairs = len(nodes) * (len(nodes) - 1) / 2
        return mirror_count / total_pairs if total_pairs > 0 else 0.0

    def _calculate_substance_vector(self, current_node):
        if not self.hlsf.field_map:
            return (0.0, 0.0)
        centroid = [0.0] * min(self.hlsf.dimension, 18)
        for node in self.hlsf.field_map.values():
            for i in range(len(centroid)):
                if i < len(node.coordinates):
                    centroid[i] += node.coordinates[i]
        count = len(self.hlsf.field_map)
        centroid = [c / count for c in centroid]
        return (centroid[0], centroid[1])


class ProprioceptionSystem:
    """Tracks Orb's physical state and computes navigation intent relative to cursor/habits."""

    def __init__(self, start_pos=[960, 540]):
        self.position = list(start_pos)
        self.target_safe_distance = 250.0  # Pixels
        self.min_safe_distance = 150.0
        self.velocity = [0.0, 0.0]
        self.last_update = time.time()

    def update_physics(self, current_pos, dt):
        dx = current_pos[0] - self.position[0]
        dy = current_pos[1] - self.position[1]
        self.velocity = [dx / dt if dt > 0 else 0, dy / dt if dt > 0 else 0]
        self.position = list(current_pos)
        self.last_update = time.time()

    def calculate_navigation_vector(self, cursor_pos, habit_heatmap, gravity_density):
        """
        Compute desire vector:
        1. Attraction to Cursor (Gravity)
        2. Repulsion from Cursor (Safe Bubble)
        3. Repulsion from Traffic (Habit Heatmap)
        4. Repulsion from High Entropy (Gravity Field)
        """
        # Vector to cursor
        dx = cursor_pos[0] - self.position[0]
        dy = cursor_pos[1] - self.position[1]
        dist = (dx**2 + dy**2) ** 0.5

        if dist == 0:
            return [0, 0]

        # 1. Attract/Repel Cursor (Goldilocks Zone)
        # If too far, attract. If too close, repel strongly.
        force_mag = 0.0
        if dist < self.min_safe_distance:
            # Strong repulsion
            force_mag = -1.0 * (self.min_safe_distance - dist) / self.min_safe_distance
        elif dist > self.target_safe_distance:
            # Gentle attraction
            force_mag = 0.5 * (dist - self.target_safe_distance) / 1000.0

        # Base vector
        nx, ny = dx / dist, dy / dist
        nav_vector = [nx * force_mag, ny * force_mag]

        # 2. Habit Avoidance (Traffic)
        # If current location is high-traffic, add slight random jitter or repulsion to keep moving
        if habit_heatmap and habit_heatmap > 0.5:
            # Add perpendicular vector to flow? Or just noise to prevent loitering
            import random

            nav_vector[0] += (random.random() - 0.5) * habit_heatmap
            nav_vector[1] += (random.random() - 0.5) * habit_heatmap

        # 3. Epistemic Gravity Repulsion (High Entropy/Density)
        # If density is high (chaotic), pull back further
        if gravity_density > 0.0:
            # Push away from cursor more
            nav_vector[0] -= nx * gravity_density * 0.5
            nav_vector[1] -= ny * gravity_density * 0.5

        return nav_vector


class SubstrateRouter:
    """
    Runtime bridge between user queries and CALI_SUBSTRATE domain knowledge.

    Implements the full pipeline:
        load_manifest() → match_query() → load_domain() → apply_strategy() → run_governance()

    CSVs in R:/CALI_SUBSTRATE/domain_knowledge are the live routing and knowledge source.
    """

    SUBSTRATE_ROOT = Path(r"R:\CALI_SUBSTRATE\domain_knowledge")
    BULK_MIRRORS_ROOT = Path(r"R:\datasets\bulk_mirrors")

    # Strategy definitions — map strategy name → ordered reasoning steps
    STRATEGIES = {
        "constraint_first": [
            "Check governance constraints and compliance rules before creative output",
            "Validate against known edge cases from substrate",
            "Apply domain knowledge with safety guardrails",
        ],
        "merge_causal": [
            "Identify causal links across both primary and secondary domains",
            "Blend domain knowledge and explain interactions",
            "Surface cross-domain implications",
        ],
        "dependency_chain": [
            "Map upstream → downstream effects",
            "Trace regulatory and procedural dependencies",
            "Order reasoning from root cause to final output",
        ],
        "weighted_balance": [
            "Score competing factors from multiple domains",
            "Weight by confidence and evidence strength",
            "Return balanced recommendation with confidence band",
        ],
        "contextual_overlay": [
            "Load primary domain knowledge as base",
            "Overlay secondary domain as contextual modifier",
            "Synthesize with temporal and market-condition awareness",
        ],
    }

    def __init__(self) -> None:
        self.manifest: dict = {}
        self.routes: list = []       # from financial_topics.csv  → keyword routing
        self.knowledge: list = []    # from financial_use_cases.csv → domain cases
        self.governance: list = []   # edge_case_handling rows across all CSVs
        self._load()

    # ------------------------------------------------------------------
    # 1. load_manifest
    # ------------------------------------------------------------------
    def load_manifest(self) -> dict:
        """Load and return the substrate manifest.json."""
        manifest_path = self.SUBSTRATE_ROOT / "manifest.json"
        if not manifest_path.exists():
            return {}
        try:
            return json.loads(manifest_path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"[SubstrateRouter] manifest load failed: {exc}", file=sys.stderr)
            return {}

    # ------------------------------------------------------------------
    # 2. load_domain
    # ------------------------------------------------------------------
    def load_domain(self, domain: str) -> list:
        """
        Load all CSV/JSON/TXT files from a named domain folder.
        Returns a flat list of dicts representing loaded records.
        """
        domain_path = self.SUBSTRATE_ROOT / domain
        if not domain_path.exists():
            return []

        records = []
        for file_path in sorted(domain_path.iterdir()):
            try:
                if file_path.suffix == ".csv":
                    with file_path.open(newline="", encoding="utf-8") as fh:
                        for row in csv.DictReader(fh):
                            records.append({**dict(row), "_source": str(file_path.name), "_domain": domain})
                elif file_path.suffix == ".json":
                    data = json.loads(file_path.read_text(encoding="utf-8"))
                    if isinstance(data, list):
                        for item in data:
                            records.append({**item, "_source": str(file_path.name), "_domain": domain})
                    elif isinstance(data, dict):
                        records.append({**data, "_source": str(file_path.name), "_domain": domain})
                elif file_path.suffix in (".txt", ".md"):
                    text = file_path.read_text(encoding="utf-8").strip()
                    records.append({"content": text, "_source": str(file_path.name), "_domain": domain})
            except Exception as exc:
                print(f"[SubstrateRouter] load_domain({domain}) file error: {exc}", file=sys.stderr)

        return records

    # ------------------------------------------------------------------
    # 3. match_query
    # ------------------------------------------------------------------
    def _load_bulk_mirror_category(self, category: str, max_files: int = 3) -> list:
        """
        Read recent JSON cache files from R:\\datasets\\bulk_mirrors\\{category}\\.
        Returns parsed records ready to merge with substrate knowledge.
        """
        mirror_dir = self.BULK_MIRRORS_ROOT / category
        if not mirror_dir.exists():
            return []
        records = []
        json_files = sorted(mirror_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
        for jf in json_files[:max_files]:
            try:
                payload = json.loads(jf.read_text(encoding="utf-8"))
                data = payload.get("data", payload)
                if isinstance(data, dict):
                    records.append({**data, "_source": jf.name, "_domain": category, "_from_mirror": True})
                elif isinstance(data, list):
                    for item in data[:5]:
                        if isinstance(item, dict):
                            records.append({**item, "_source": jf.name, "_domain": category, "_from_mirror": True})
            except Exception:
                continue
        return records

    def match_query(self, query: str) -> dict:
        """
        Score query against loaded routes to determine:
          - primary_domain
          - secondary_domains
          - strategy
          - matched_cases (relevant knowledge rows)
          - governance_flags (applicable edge cases)
        """
        q = query.lower()
        tokens = set(q.split())

        domain_scores: dict = {}
        matched_cases: list = []
        governance_flags: list = []

        # Score routes (from financial_topics.csv and similar routing CSVs)
        for route in self.routes:
            keywords = set(k.strip().lower() for k in route.get("keywords", "").split(",") if k.strip())
            tags = set(t.strip().lower() for t in route.get("semantic_tags", "").split(",") if t.strip())
            combined = keywords | tags | {route.get("id", "").lower()} | {route.get("name", "").lower().replace(" ", "_")}
            overlap = tokens & combined
            if not overlap:
                # Also try substring match for longer phrases
                phrase = route.get("name", "").lower()
                if phrase and phrase in q:
                    overlap = {phrase}
            if overlap:
                score = len(overlap) / max(len(combined), 1)
                domain = route.get("_domain", "financial_knowledge")
                domain_scores[domain] = domain_scores.get(domain, 0.0) + score
                # Collect cross-domain links
                for link in route.get("cross_domain_links", "").split(","):
                    link = link.strip()
                    if link:
                        domain_scores[link] = domain_scores.get(link, 0.0) + score * 0.4

        # Score knowledge cases (from financial_use_cases.csv)
        for case in self.knowledge:
            case_text = " ".join([
                case.get("name", ""),
                case.get("description", ""),
                case.get("implications", ""),
                case.get("category", ""),
            ]).lower()
            case_tokens = set(case_text.split())
            if tokens & case_tokens:
                matched_cases.append(case)

        # Collect governance flags for matched routes / cases
        for g_row in self.governance:
            edge = g_row.get("edge_case_handling", "").lower()
            if any(tok in edge for tok in tokens):
                governance_flags.append(g_row.get("edge_case_handling", ""))

        if not domain_scores:
            return {"primary_domain": None, "secondary_domains": [], "strategy": None,
                    "matched_cases": [], "governance_flags": [], "mirror_records": []}

        sorted_domains = sorted(domain_scores, key=domain_scores.get, reverse=True)
        primary = sorted_domains[0]
        secondary = sorted_domains[1:3]
        strategy = self._pick_strategy(primary, secondary, q)

        # Pull from bulk_mirrors for the matched domains
        mirror_category_map = {
            "financial_knowledge": "financial_economic",
            "macro_economic_knowledge": "macro_economic_indicators",
            "micro_economic_knowledge": "micro_economic_markets",
            "medical_knowledge": "biomedical_and_public_health",
            "industrial_knowledge": "industrial_manufacturing",
            "research_layer": "scientific_literature_and_evidence",
        }
        mirror_records: list = []
        for dom in [primary] + list(secondary):
            cat = mirror_category_map.get(dom, dom)
            mirror_records.extend(self._load_bulk_mirror_category(cat, max_files=2))

        return {
            "primary_domain": primary,
            "secondary_domains": secondary,
            "strategy": strategy,
            "matched_cases": matched_cases[:5],
            "governance_flags": governance_flags[:5],
            "domain_scores": domain_scores,
            "mirror_records": mirror_records[:10],
        }

    # ------------------------------------------------------------------
    # 4. apply_strategy
    # ------------------------------------------------------------------
    def apply_strategy(self, strategy: str, query: str, route_match: dict) -> dict:
        """
        Return a structured reasoning plan for the matched strategy.
        Used to annotate the thought object before final verdict.
        """
        steps = self.STRATEGIES.get(strategy, self.STRATEGIES["weighted_balance"])
        cases = route_match.get("matched_cases", [])
        knowledge_snippets = [
            f"{c.get('name', '')}: {c.get('description', '')} | {c.get('implications', '')}"
            for c in cases[:3]
        ]
        return {
            "strategy": strategy,
            "steps": steps,
            "primary_domain": route_match.get("primary_domain"),
            "secondary_domains": route_match.get("secondary_domains", []),
            "knowledge_snippets": knowledge_snippets,
            "query": query,
        }

    # ------------------------------------------------------------------
    # 5. run_governance
    # ------------------------------------------------------------------
    def run_governance(self, query: str, reasoning_result: dict, route_match: dict) -> dict:
        """
        Pre-output governance check using substrate edge_case_handling rules.
        Returns a governance report with any triggered flags and a pass/warn verdict.
        """
        flags = route_match.get("governance_flags", [])
        triggered = []
        q = query.lower()

        # Built-in safety checks
        if any(k in q for k in ("credential", "password", "secret", "token", "api_key")):
            triggered.append("GOVERNANCE: Hardcoded credentials detected — reject or redact.")
        if any(k in q for k in ("delete all", "drop table", "truncate", "rm -rf")):
            triggered.append("GOVERNANCE: Destructive operation pattern — escalate for review.")

        # Substrate-derived edge case flags
        for flag in flags:
            triggered.append(f"SUBSTRATE CONSTRAINT: {flag}")

        verdict = "WARN" if triggered else "PASS"
        return {
            "verdict": verdict,
            "triggered_rules": triggered,
            "checked_flags": len(flags),
            "query_snapshot": query[:120],
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _load(self) -> None:
        self.manifest = self.load_manifest()
        domains = self.manifest.get("new_domains", []) or list(
            d.name for d in self.SUBSTRATE_ROOT.iterdir()
            if d.is_dir() and not d.name.startswith("_")
        ) if self.SUBSTRATE_ROOT.exists() else []

        for domain in domains:
            records = self.load_domain(domain)
            for rec in records:
                src = rec.get("_source", "")
                if "topics" in src or "routes" in src or "routing" in src:
                    self.routes.append(rec)
                elif "use_case" in src or "cases" in src or "knowledge" in src:
                    self.knowledge.append(rec)
                else:
                    # Default: treat as routing route if it has keywords, else knowledge
                    if rec.get("keywords") or rec.get("semantic_tags"):
                        self.routes.append(rec)
                    else:
                        self.knowledge.append(rec)
                # All rows contribute governance edge cases
                if rec.get("edge_case_handling"):
                    self.governance.append(rec)

        print(
            f"[SubstrateRouter] Loaded: {len(self.routes)} routes, "
            f"{len(self.knowledge)} knowledge entries, "
            f"{len(self.governance)} governance rules",
            flush=True,
        )

    def _pick_strategy(self, primary: str, secondary: list, query: str) -> str:
        """Choose a reasoning strategy based on domain combination and query signals."""
        q = query.lower()
        has_secondary = bool(secondary)

        if any(k in q for k in ("compliance", "audit", "regulation", "filing", "sec", "governance")):
            return "constraint_first"
        if any(k in q for k in ("risk", "rate", "shift", "crash", "regime")):
            return "weighted_balance"
        if has_secondary and any(k in q for k in ("billing", "medical", "telemedicine", "clinical")):
            return "merge_causal"
        if any(k in q for k in ("upstream", "downstream", "chain", "dependency", "workflow")):
            return "dependency_chain"
        if has_secondary:
            return "contextual_overlay"
        return "weighted_balance"


class SF_ORB_Controller:
    """Canonical Triple Triple Controller (Triad C)."""

    def __init__(self, cali=None):
        print("Initializing SF-ORB Sovereign Logic...")
        self.engine = hlsf_singleton
        self.tribunal = FourMindTribunal(skg_path="components/core_4_minds")
        system_root = Path(
            os.getenv("ORB_SYSTEM_ROOT", Path(__file__).resolve().parents[2])
        ).resolve()
        vault_root = Path(
            os.getenv("ORB_VAULT_ROOT", str(system_root / "vault_system"))
        ).expanduser().resolve()
        self.vaults = VaultManager(base_path=str(vault_root))
        self.habit_tracker = HabitTracker(self.vaults)
        self.intuitive_recognizer = IntuitiveRecognizer(self.engine)
        self.gravity_bridge = EpistemicGravityBridge()
        self.proprioception = ProprioceptionSystem()
        self.bayes = BayesianEngine(alpha=1.5, beta=1.0)
        self.swarm_extension = None
        repo_root = Path(__file__).resolve().parent
        self.spinoza_engine = SpinozaEngine(repo_root)
        if cali is not None:
            self.cali = cali
        elif os.getenv("ORB_CONTROLLER_ATTACH_CALI", "0").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }:
            try:
                from cali_skg import CALISKG as ImportedCALISKG

                global CALISKG
                CALISKG = ImportedCALISKG
                self.cali = CALISKG(system_root)
                print(f"✓ CALI SKG attached to controller at {system_root}", flush=True)
            except Exception as exc:
                self.cali = None
                print(f"⚠️ CALI SKG unavailable: {exc}", flush=True)
        else:
            self.cali = None
        self.substrate_router = SubstrateRouter()
        self._initialize_bayesian_priors()
        print("✓ Triple Triple Architecture Online")
        print("✓ Logic Triad C: Deductive | Inductive | Intuitive")
        print("✓ Substrate Router: CALI_SUBSTRATE domain knowledge wired")

    def emergency_purge(self):
        """Manual density reset to restore SLA."""
        before = len(self.engine.field_map)
        if before > 1000:
            self.engine._edge_cutter_purge()
            after = len(self.engine.field_map)
            print(f"🧹 EMERGENCY PURGE: {before} → {after} nodes")
            return True
        return False

    def cognitively_emerge(self, stimulus):
        start_time = time.time()

        if not self._check_sovereignty(stimulus):
            return None

        self.habit_tracker.record_observation(stimulus)

        gravity_stats = self.gravity_bridge.process_stimulus(stimulus)

        # Proprioception Update (Assuming stimulus contains Orb pos, or we simulate it)
        # Since we don't have Orb pos in stimulus commonly, we use the controller's estimation or previous intent
        # For now, we simulate "Proprioception" updating its own belief based on the previous command
        # Ideally, stimulus['orb_coordinates'] should be passed.
        orb_pos = stimulus.get("orb_coordinates", self.proprioception.position)
        self.proprioception.update_physics(orb_pos, 0.1)  # dt approx 0.1s

        # Navigation Logic
        cursor_pos = stimulus.get("coordinates", [0, 0])
        gravity_density = gravity_stats.get("renewal_pressure", 0.0)

        # Get habit heat for current orb position
        current_orb_quad = self.habit_tracker._coords_to_quadrant(
            self.proprioception.position
        )
        habit_heat = self.habit_tracker.get_quadrant_heat(current_orb_quad)

        nav_vector = self.proprioception.calculate_navigation_vector(
            cursor_pos, habit_heat, gravity_density
        )

        node = self.engine.map_adjacency(stimulus)

        intuition = self.intuitive_recognizer.check_necessity(stimulus, node)
        inductive = (
            None
            if intuition.get("jump_triggered")
            else self.habit_tracker.predict_next()
        )

        bypass = self.vaults.lightning_query(stimulus)
        if bypass:
            elapsed = (time.time() - start_time) * 1000
            print(f"⚡ LIGHTNING BYPASS ({elapsed:.2f}ms)")
            return bypass

        shadows = self.tribunal.generate_epistemic_shadow(stimulus)
        bayes_shadows = self._update_bayesian_shadows(shadows)

        logic_state = self._synthesize_logic_triad(inductive, intuition, bayes_shadows)

        neighbors = self.engine.get_recursive_neighbors(node, radius=3)
        thought_vec = (
            self.engine.calculate_thought_vector(neighbors + [node])
            if neighbors
            else (0.0,) * self.engine.dimension
        )

        confidence = self._calculate_convergence(shadows, logic_state, thought_vec)

        spatial_coord = {
            "node_id": f"NODE_{node.n}_{node.k}",
            "recursion_depth": node.k,
            "coordinates": node.coordinates,
            "adjacency_value": node.adjacency_value,
        }

        thought = CrossDomainPredicate(
            epistemic=shadows,
            spatial=spatial_coord,
            logic=logic_state,
            synthesis_confidence=confidence,
        )
        thought.gravity_stats = gravity_stats
        thought.egf_visual_state = self.gravity_bridge.get_visual_state(gravity_stats)
        thought.navigation_vector = nav_vector

        # All cognition is parallel. All convergence is advisory. All execution is downstream.
        ucm_envelope = self._build_correlation_envelope(
            stimulus=stimulus,
            shadows=shadows,
            bayes_shadows=bayes_shadows,
            logic_state=logic_state,
            confidence=confidence,
        )
        cali_reflection = ucm_envelope.get("cali_reflection", {})

        thought.ucm_envelope = ucm_envelope
        thought.cali_reflection = cali_reflection
        thought.final_verdict = ucm_envelope.get("final_verdict")
        thought.final_verdict_source = ucm_envelope.get("final_verdict_source")

        # Spinoza SKG single-lobe reasoning (deterministic philosophical layer)
        query_text = self._stimulus_to_query(stimulus)
        try:
            spinoza_result = self.spinoza_engine.reason(query_text)
            thought.spinoza = spinoza_result
            if spinoza_result.get("verdict"):
                thought.final_verdict = spinoza_result["verdict"]
                thought.final_verdict_source = "Spinoza_SKG"
        except Exception as exc:
            print(f"⚠️ Spinoza reasoning failed: {exc}")

        # ── SUBSTRATE ROUTING ────────────────────────────────────────────────
        # Step 1: match query against CALI_SUBSTRATE domain knowledge
        route_match = {}
        strategy_plan = {}
        try:
            route_match = self.substrate_router.match_query(query_text)
            if route_match.get("strategy"):
                strategy_plan = self.substrate_router.apply_strategy(
                    route_match["strategy"], query_text, route_match
                )
                thought.substrate_route = route_match
                thought.strategy_plan = strategy_plan
                print(
                    f"[Substrate] domain={route_match.get('primary_domain')} "
                    f"strategy={route_match.get('strategy')} "
                    f"cases={len(route_match.get('matched_cases', []))}",
                    flush=True,
                )
        except Exception as exc:
            print(f"⚠️ Substrate routing failed: {exc}", file=sys.stderr)
        # ── END SUBSTRATE ROUTING ────────────────────────────────────────────

        if self.cali:
            try:
                # Pass substrate route context into CALI reasoning when available
                cali_context = {}
                if route_match.get("primary_domain"):
                    cali_context["substrate_domain"] = route_match["primary_domain"]
                    cali_context["substrate_strategy"] = route_match.get("strategy")
                    cali_context["matched_cases"] = [
                        c.get("name", "") for c in route_match.get("matched_cases", [])
                    ]
                skg_result = self.cali.reason(query_text, context=cali_context)
                thought.philosophical = skg_result
                advisory = skg_result.get("advisory_verdict") or {}
                verdict = advisory.get("verdict") or skg_result.get("recommended_response")
                if verdict:
                    # Enrich verdict with substrate case context when relevant
                    snippets = strategy_plan.get("knowledge_snippets", [])
                    if snippets:
                        verdict = verdict + " [Domain context: " + " / ".join(snippets[:2]) + "]"
                    thought.final_verdict = verdict
                    thought.final_verdict_source = "CALI_SKG+Substrate"
            except Exception as exc:
                print(f"⚠️ CALI SKG reasoning failed: {exc}")

        # ── GOVERNANCE CHECK ─────────────────────────────────────────────────
        # Step 2: run governance rules after reasoning, before crystallizing
        try:
            gov_result = self.substrate_router.run_governance(
                query_text,
                getattr(thought, "philosophical", {}),
                route_match,
            )
            thought.governance = gov_result
            if gov_result.get("verdict") == "WARN":
                print(
                    f"[Governance WARN] {'; '.join(gov_result.get('triggered_rules', [])[:2])}",
                    flush=True,
                )
        except Exception as exc:
            print(f"⚠️ Governance check failed: {exc}", file=sys.stderr)
        # ── END GOVERNANCE CHECK ─────────────────────────────────────────────

        self._update_bayesian_outcome(logic_state)

        self.vaults.crystallize(
            stimulus,
            {
                "predicate": thought.pulse(),
                "confidence": confidence,
                "triad_c_mode": logic_state.get("active_mode"),
                "field_density": logic_state.get("field_density", 0),
                "ucm_envelope": ucm_envelope,
                "cali_reflection": cali_reflection,
            },
        )

        elapsed = (time.time() - start_time) * 1000
        mode = logic_state.get("active_mode", "GUARD")
        print(
            f"🧠 [{mode}] {elapsed:.1f}ms | Density: {logic_state.get('field_density', 0)}"
        )
        self._notify_swarm_extension(stimulus, thought)

        return thought

    def idle_cognition(self, stimulus):
        """Compatibility hook for idle reflection producers."""
        payload = dict(stimulus or {})
        payload.setdefault("type", "idle_reflection")
        payload.setdefault("intent", "reflection")
        payload.setdefault("coordinates", [0, 0])
        payload.setdefault("velocity", 0.0)
        return self.cognitively_emerge(payload)

    def shutdown(self):
        """Lifecycle hook for external managers."""
        if self.swarm_extension and hasattr(self.swarm_extension, "shutdown"):
            try:
                self.swarm_extension.shutdown()
            except Exception:
                pass
        return True

    def attach_swarm_extension(self, extension):
        self.swarm_extension = extension

    def _notify_swarm_extension(self, stimulus, thought):
        if not self.swarm_extension:
            return
        if not hasattr(self.swarm_extension, "ingest_stimulus"):
            return
        try:
            self.swarm_extension.ingest_stimulus(stimulus, thought)
        except Exception as exc:
            print(f"[Swarm Extension Error] {exc}", flush=True)

    def _stimulus_to_query(self, stimulus: dict) -> str:
        stype = stimulus.get("type", "stimulus")
        coords = stimulus.get("coordinates") or stimulus.get("orb_coordinates") or [0, 0]
        velocity = stimulus.get("velocity", 0.0)
        intent = stimulus.get("intent", "observation")
        return f"{stype} at {coords} velocity {velocity} intent {intent}"

    def _build_correlation_envelope(
        self, stimulus, shadows, bayes_shadows, logic_state, confidence
    ):
        stardate = time.time()
        glyph_trace = self._glyph_trace(stimulus, stardate)
        core_4 = self._build_core_4_returns(shadows, bayes_shadows, logic_state)
        advisory_plus_one = self._build_advisory_plus_one(core_4)
        cali_reflection = self._build_cali_reflection(advisory_plus_one, logic_state)
        final_verdict = self._verdict_from_mode(logic_state.get("active_mode"))

        return {
            "stardate": stardate,
            "glyph_trace": glyph_trace,
            "core_4": core_4,
            "advisory_plus_one": advisory_plus_one,
            "cali_reflection": cali_reflection,
            "final_verdict": final_verdict,
            "final_verdict_source": "UCM Core-4 deliberation (ECM advisory only)",
            "confidence": confidence,
        }

    def _build_core_4_returns(self, shadows, bayes_shadows, logic_state):
        caleon_shadow = shadows.get("spinoza", {})
        kaygee_shadow = shadows.get("kant", {})
        cali_shadow = shadows.get("hume", {})
        locke_shadow = shadows.get("locke", {})

        advisory_verdict = self._verdict_from_mode(logic_state.get("active_mode"))
        convergence_weights = self._normalize_weights(
            {
                "caleon": caleon_shadow.get("confidence", 0.5),
                "kaygee": kaygee_shadow.get("confidence", 0.5),
                "cali_x_one": cali_shadow.get("confidence", 0.5),
                "empirical": locke_shadow.get("confidence", 0.5),
            }
        )

        return {
            "caleon": {
                "shadow": caleon_shadow,
                "confidence": caleon_shadow.get("confidence", 0.5),
                "advisory_verdict": advisory_verdict,
            },
            "kaygee": {
                "shadow": kaygee_shadow,
                "confidence": kaygee_shadow.get("confidence", 0.5),
                "advisory_verdict": advisory_verdict,
            },
            "cali_x_one": {
                "shadow": cali_shadow,
                "confidence": cali_shadow.get("confidence", 0.5),
                "advisory_verdict": advisory_verdict,
            },
            "ecm": {
                "convergence_weights": convergence_weights,
                "inputs": {
                    "locke": locke_shadow,
                    "hume": cali_shadow,
                    "kant": kaygee_shadow,
                    "spinoza": caleon_shadow,
                },
                "note": "ECM emits convergence weights only (advisory).",
            },
        }

    def _build_advisory_plus_one(self, core_4):
        confidences = {
            "caleon": core_4.get("caleon", {}).get("confidence", 0.5),
            "kaygee": core_4.get("kaygee", {}).get("confidence", 0.5),
            "cali_x_one": core_4.get("cali_x_one", {}).get("confidence", 0.5),
        }
        weights = self._softmax(list(confidences.values()))
        gradients = dict(zip(confidences.keys(), weights))

        entropy = -sum(p * math.log(p + 1e-9) for p in weights)
        spread = (
            max(confidences.values()) - min(confidences.values())
            if confidences
            else 0.0
        )
        reweight = entropy > 1.0 or spread > 0.2

        return {
            "advisory_only": True,
            "confidence_gradients": gradients,
            "tension_indicators": {
                "entropy": entropy,
                "spread": spread,
                "reweight_recommended": reweight,
            },
            "suggestion": (
                "consider re-weighting high-tension lobes"
                if reweight
                else "no reweight suggested"
            ),
        }

    def _build_cali_reflection(self, advisory_plus_one, logic_state):
        tension = advisory_plus_one.get("tension_indicators", {})
        entropy = tension.get("entropy", 0.0)
        spread = tension.get("spread", 0.0)

        events = []
        if spread > 0.2:
            events.append(
                {"type": "drift", "detail": "confidence spread exceeded threshold"}
            )
        if entropy > 1.0:
            events.append(
                {"type": "anomaly", "detail": "high entropy in lobe gradients"}
            )
        if logic_state.get("active_mode") == "INTUITION-JUMP" and entropy > 0.9:
            events.append(
                {"type": "tension", "detail": "intuition jump under high entropy"}
            )

        return {
            "observational_only": True,
            "events": events,
            "flags": {
                "drift_detected": any(e["type"] == "drift" for e in events),
                "anomaly_detected": any(e["type"] == "anomaly" for e in events),
                "ethical_tension": any(e["type"] == "tension" for e in events),
            },
        }

    def _verdict_from_mode(self, mode):
        if mode == "INTUITION-JUMP":
            return "escalate"
        if mode == "HABIT":
            return "act"
        if mode == "GUARD-HABIT":
            return "monitor"
        return "no_act"

    def _glyph_trace(self, stimulus, stardate):
        canonical = json.dumps(stimulus, sort_keys=True, default=str)
        payload = f"{stardate}:{canonical}"
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _softmax(self, values):
        if not values:
            return []
        max_val = max(values)
        exps = [math.exp(v - max_val) for v in values]
        total = sum(exps) or 1.0
        return [e / total for e in exps]

    def _normalize_weights(self, weights):
        total = sum(weights.values()) or 1.0
        return {k: v / total for k, v in weights.items()}

    def _check_sovereignty(self, stimulus):
        if stimulus.get("meta", {}).get("test_mode") is True:
            return True
        if stimulus.get("type") == "surveillance_probe":
            print("⛔ SOVEREIGNTY VIOLATION: Surveillance detected")
            return False
        return True

    def _synthesize_logic_triad(self, inductive, intuitive, bayes_shadows):
        live_density = len(self.engine.field_map)
        breach_density = getattr(self.engine, "last_density_breach", 0)
        effective_density = max(live_density, breach_density)
        state = {"field_density": effective_density, "active_mode": "GUARD"}
        if intuitive.get("jump_triggered"):
            state.update(
                {
                    "intuitive_jump_triggered": True,
                    "necessity_vector": intuitive.get("necessity_vector"),
                    "spinozan_certainty": intuitive.get("spinozan_certainty"),
                    "active_mode": "INTUITION-JUMP",
                    "substance_unity_score": intuitive.get("substance_unity_score"),
                }
            )
            return state
        if inductive:
            confidence = inductive.get("confidence", 0)
            state.update(
                {
                    "inductive_prediction": inductive,
                    "hume_vivacity": inductive.get("hume_vivacity", 0),
                    "custom_habit_active": confidence > 0.35,
                    "active_mode": "HABIT" if confidence > 0.35 else "GUARD-HABIT",
                }
            )
        habit_post = self.bayes.calculate_posterior("habit_continues") or 0.0
        jump_post = self.bayes.calculate_posterior("jump_necessary") or 0.0
        guard_post = self.bayes.calculate_posterior("guard_sufficient") or 0.0
        state.update(
            {
                "bayes_habit_prob": habit_post,
                "bayes_jump_prob": jump_post,
                "bayes_guard_prob": guard_post,
                "epistemic_bayes": bayes_shadows,
            }
        )
        # Apply space-field pressure: high density should bias away from inert GUARD.
        density = state.get("field_density", 0)
        if (
            state.get("active_mode") in ("GUARD", "GUARD-HABIT")
            and density >= self.engine.purge_trigger_threshold
        ):
            state["active_mode"] = "GUARD-HABIT"
            state["density_penalty"] = 1.0
            print(f"🚫 GUARD INVALIDATED: Density {density} → Forced GUARD-HABIT")
        if (
            density >= self.engine.max_field_density * 0.95
            and state.get("active_mode") != "INTUITION-JUMP"
        ):
            state["active_mode"] = "INTUITION-JUMP"
            state["density_penalty"] = 1.5
            print(f"🚨 EMERGENCY JUMP: Critical density {density}")
        if state.get("active_mode") in ("GUARD", "GUARD-HABIT") and habit_post > 0.55:
            state["active_mode"] = "HABIT"
        if state.get("active_mode") != "INTUITION-JUMP" and jump_post > 0.45:
            state["active_mode"] = "INTUITION-JUMP"
        if (
            density >= self.engine.purge_trigger_threshold
            and state.get("active_mode") == "GUARD"
        ):
            print(
                f"CRITICAL: GUARD survived density breach ({density}) — enforcement failed!"
            )
        return state

    def _calculate_convergence(self, shadows, logic, thought_vec):
        base = 0.85
        if logic.get("intuitive_jump_triggered"):
            base += 0.14
        elif logic.get("custom_habit_active"):
            base += 0.08
        if len(shadows) >= 3:
            base += 0.02
        vec_magnitude = sum(abs(v) for v in thought_vec) if thought_vec else 0.0
        base += min(vec_magnitude * 0.001, 0.02)
        return min(base, 0.99)

    def _initialize_bayesian_priors(self):
        seed_priors = {
            "habit_continues": (0.6, 1.2),
            "jump_necessary": (0.3, 0.8),
            "guard_sufficient": (0.7, 1.5),
        }
        for hyp, (prob, strength) in seed_priors.items():
            self.bayes.set_prior(hyp, prob, evidence_strength=strength)
            self.bayes.add_evidence(
                hypothesis=hyp,
                evidence_id=f"seed_{hyp}",
                likelihood=prob,
                source="init",
                reliability=0.01,
            )

    def _update_bayesian_shadows(self, shadows):
        bayes_view = {}
        timestamp_id = f"stim_{int(time.time()*1000)}"
        for mind_name, shadow in shadows.items():
            hyp = f"{mind_name}_pattern_persistence"
            likelihood = shadow.get("confidence", 0.5)
            reliability = shadow.get("reliability", 1.0)
            if hyp not in self.bayes.priors:
                self.bayes.set_prior(hyp, 0.5, evidence_strength=1.0)
            self.bayes.add_evidence(
                hypothesis=hyp,
                evidence_id=f"{timestamp_id}_{mind_name}",
                likelihood=likelihood,
                source=mind_name,
                reliability=reliability,
            )
            bayes_view[mind_name] = self.bayes.calculate_posterior(hyp) or likelihood
        return bayes_view

    def _update_bayesian_outcome(self, logic_state):
        mode = logic_state.get("active_mode", "GUARD")
        pred = logic_state.get("inductive_prediction", {}) or {}
        success = mode in ("HABIT", "GUARD-HABIT") and pred.get("confidence", 0) > 0.4
        self.bayes.update_with_outcome("habit_continues", success=success, weight=0.7)
        jump_success = mode == "INTUITION-JUMP" and logic_state.get(
            "intuitive_jump_triggered"
        )
        self.bayes.update_with_outcome(
            "jump_necessary", success=bool(jump_success), weight=0.6
        )
        guard_success = mode == "GUARD" and not success and not jump_success
        self.bayes.update_with_outcome(
            "guard_sufficient", success=guard_success, weight=0.5
        )


if __name__ == "__main__":
    orb = SF_ORB_Controller()
    sample = {
        "type": "cursor_movement",
        "coordinates": [100, 200],
        "velocity": 5.0,
        "intent": "navigation",
        "meta": {"test_mode": True},
    }
    orb.cognitively_emerge(sample)
