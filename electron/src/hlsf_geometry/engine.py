import math
import random
import sys
from typing import Dict, List, Tuple
from dataclasses import dataclass, field


@dataclass
class HLSFNode:
    """A coordinate in the High-Level Space Field"""

    n: int  # Scale dimension
    k: int  # Recursion depth
    coordinates: Tuple[float, ...]
    adjacency_value: float = 0.0
    cognitive_load: float = 1.0
    occupied_by: List[str] = field(default_factory=list)

    def recursive_adjacency(self, other: "HLSFNode") -> float:
        """Calculate A(n,k) = n * A(n,k-1) between two nodes"""
        if self.n == 0 or self.k == 0:
            return 0.0
        base_adj = abs(self.n - other.n) * math.exp(-abs(self.k - other.k))
        return self.n * base_adj


class HLSFEngine:
    def __init__(self, dimension: int = 18):
        self.dimension = dimension
        self.field_map: Dict[str, HLSFNode] = {}
        self.cursor_position = (0.0,) * dimension
        self.pulse_frequency = 0.0
        self.max_field_density = 1000
        self.purge_trigger_threshold = 800  # soft warning / purge trigger
        self.purge_release_threshold = 650  # hysteresis release to prevent oscillation
        self.edge_cutter_threshold = (
            self.purge_trigger_threshold
        )  # backward compatibility
        self.purge_keep_ratio = 0.6
        self.edge_cutter_active = False
        self.hysteresis_band = (
            self.purge_trigger_threshold - self.purge_release_threshold
        )
        self.last_density_breach = (
            0  # remembers last pre-purge density for causal enforcement
        )
        import sys

        print(
            f"Hysteresis active: trigger {self.purge_trigger_threshold} -> release {self.purge_release_threshold} "
            f"(band: {self.hysteresis_band} nodes) | Hard cap: {self.max_field_density}",
            file=sys.stderr,
        )

    def map_adjacency(self, stimulus: dict) -> HLSFNode:
        """Map stimulus to HLSF coordinate space with edge-cutter guardrails."""
        stimulus_hash = str(hash(str(stimulus)))[-8:]
        n_val = int(stimulus_hash[:4]) % self.dimension + 1
        k_val = int(stimulus_hash[4:]) % 10 + 1

        coords = self._generate_coordinates(stimulus)
        node_id = f"NODE_{n_val}_{k_val}_{hash(coords)}"

        node_obj = None
        if node_id not in self.field_map:
            intensity = stimulus.get("intensity", 0.5)
            velocity = stimulus.get("velocity", 0.0)
            initial_vivacity = 1.0 + (velocity / 5.0) + (intensity * 3.0)
            node = HLSFNode(
                n=n_val,
                k=k_val,
                coordinates=coords,
                cognitive_load=min(initial_vivacity, 10.0),
            )
            self.field_map[node_id] = node
            node_obj = node
        else:
            node = self.field_map[node_id]
            repetition_count = (
                len(node.occupied_by) if isinstance(node.occupied_by, list) else 0
            )
            repetition_boost = 0.3 + 0.2 * math.log1p(repetition_count)
            intensity = stimulus.get("intensity", 0.5)
            velocity = stimulus.get("velocity", 0.0)
            intensity_boost = intensity * 1.5
            velocity_boost = velocity / 10.0
            node.cognitive_load = min(
                node.cognitive_load
                + repetition_boost
                + intensity_boost
                + velocity_boost,
                10.0,
            )
            if repetition_count <= 2 and node.cognitive_load < 1.5:
                node.cognitive_load = 1.5  # Prevent premature purge of newborn nodes
            node_obj = node

        current_density = len(self.field_map)

        # Hysteresis: deactivate once we drift below the release threshold so growth can resume before next purge.
        if self.edge_cutter_active and current_density <= self.purge_release_threshold:
            self.edge_cutter_active = False
            self.last_density_breach = 0
        should_purge = current_density >= self.max_field_density or (
            not self.edge_cutter_active
            and current_density >= self.purge_trigger_threshold
        )

        if should_purge:
            self.last_density_breach = current_density
            sys.stderr.write(
                "Density warning: {}/{} (release {}). Triggering edge-cutter...\n".format(
                    current_density,
                    self.purge_trigger_threshold,
                    self.purge_release_threshold,
                )
            )
            # Preserve the current node across purge so callers never see a missing key.
            self._edge_cutter_purge(
                preserve_node_id=node_id, preserve_node=self.field_map.get(node_id)
            )

        # After purge, the just-touched node might have been removed; reinsert if needed to prevent KeyError.
        node_ref = self.field_map.get(node_id)
        if node_ref is None and node_obj is not None:
            sys.stderr.write(f"DEBUG: Node {node_id} purged during add -- recreating\n")
            self.field_map[node_id] = node_obj
            node_ref = node_obj

        return node_ref

    def get_recursive_neighbors(
        self, center_node: HLSFNode, radius: int = 3
    ) -> List[HLSFNode]:
        """Retrieve adjacent nodes; sample when dense to avoid O(n) blowups."""
        if len(self.field_map) > 500:
            return self._sampled_neighbors(center_node, radius, sample_size=100)

        neighbors = []
        for node in self.field_map.values():
            if node == center_node:
                continue
            adjacency = center_node.recursive_adjacency(node)
            if 0 < adjacency <= radius:
                neighbors.append(node)
        neighbors.sort(key=lambda x: center_node.recursive_adjacency(x))
        return neighbors[:10]

    def _sampled_neighbors(
        self, center_node: HLSFNode, radius: int, sample_size: int
    ) -> List[HLSFNode]:
        samples = random.sample(
            list(self.field_map.values()), min(sample_size, len(self.field_map))
        )
        neighbors = [
            n
            for n in samples
            if n != center_node and 0 < center_node.recursive_adjacency(n) <= radius
        ]
        return sorted(neighbors, key=lambda x: center_node.recursive_adjacency(x))[:5]

    def _generate_coordinates(self, stimulus: dict) -> Tuple[float, ...]:
        """Generate high-dimensional coordinates from stimulus hash"""
        seed = str(stimulus)
        coords = []
        for i in range(self.dimension):
            # Deterministic pseudo-random from seed
            hash_val = hash(seed + str(i)) % 1000 / 1000.0
            coords.append(hash_val * 2 - 1)  # Normalize to -1, 1
        return tuple(coords)

    def calculate_thought_vector(self, nodes: List[HLSFNode]) -> Tuple[float, ...]:
        """Compute emergent vector weighted by cognitive load."""
        if not nodes:
            return (0.0,) * self.dimension

        vector = [0.0] * self.dimension
        total_weight = 0.0

        for node in nodes:
            weight = node.cognitive_load * (1.0 + node.adjacency_value)
            for i, coord in enumerate(node.coordinates):
                if i < self.dimension:
                    vector[i] += coord * weight
            total_weight += weight

        if total_weight > 0:
            vector = [v / total_weight for v in vector]

        return tuple(vector)

    def _edge_cutter_purge(self, preserve_node_id=None, preserve_node=None):
        """Sovereign forgetting: preserve top cognitive_load nodes and keep the current node resident."""
        current_density = len(self.field_map)
        # Trigger purge at the soft threshold; allow emergency purge past the hard cap.
        if (
            current_density <= self.purge_trigger_threshold
            and current_density <= self.max_field_density
        ):
            return

        if current_density > self.max_field_density:
            print(
                f"⚠️ HARD CAP VIOLATION: {current_density}/{self.max_field_density} — forced purge"
            )

        sorted_nodes = sorted(
            self.field_map.values(), key=lambda n: n.cognitive_load, reverse=True
        )

        # Cap survivors below the release threshold so hysteresis can reset immediately after purge.
        soft_keep_cap = max(1, self.purge_release_threshold - 1)
        target_keep = min(
            max(int(self.max_field_density * self.purge_keep_ratio), 1),
            soft_keep_cap,
            len(sorted_nodes),
        )

        vivacity_floor = 1.5
        keep_nodes = []
        for n in sorted_nodes:
            if n.cognitive_load >= vivacity_floor:
                keep_nodes.append(n)
            if len(keep_nodes) >= target_keep:
                break

        if len(keep_nodes) < max(1, target_keep // 2):
            keep_nodes = sorted_nodes[:target_keep]

        avg_load_kept = (
            sum(n.cognitive_load for n in keep_nodes) / len(keep_nodes)
            if keep_nodes
            else 0.0
        )

        # Ensure the just-touched node survives the purge to avoid KeyError in caller.
        existing_ids = {f"NODE_{n.n}_{n.k}_{hash(n.coordinates)}" for n in keep_nodes}
        if preserve_node_id and preserve_node:
            if preserve_node_id not in existing_ids:
                keep_nodes.insert(0, preserve_node)
            else:
                # Move the preserved node to the front to guarantee it survives slicing.
                keep_nodes = [preserve_node] + [
                    n
                    for n in keep_nodes
                    if f"NODE_{n.n}_{n.k}_{hash(n.coordinates)}" != preserve_node_id
                ]

        # Rebuild the field map with survivors (cap at hard limit but also honor soft keep cap).
        max_allowed = min(self.max_field_density, soft_keep_cap)
        self.field_map = {}
        for n in keep_nodes[:max_allowed]:
            new_id = f"NODE_{n.n}_{n.k}_{hash(n.coordinates)}"
            self.field_map[new_id] = n

        purged = current_density - len(self.field_map)
        self.edge_cutter_active = True
        print(
            f"⚡ EDGE-CUTTER: purged={purged} | kept={len(self.field_map)} | "
            f"new_density={len(self.field_map)} | avg_load_kept={avg_load_kept:.2f} | "
            f"band={self.hysteresis_band} (trigger={self.purge_trigger_threshold}, release={self.purge_release_threshold})"
        )

    def pulse(self) -> dict:
        self.pulse_frequency = (self.pulse_frequency + 0.1) % (2 * math.pi)
        return {
            "frequency": self.pulse_frequency,
            "field_density": len(self.field_map),
            "edge_cutter_active": self.edge_cutter_active,
        }

    def decay_vivacity(self, decay_factor: float = 0.99, floor: float = 0.5) -> None:
        """Slow natural fade of cognitive_load to allow true forgetting during idle periods."""
        for node in self.field_map.values():
            node.cognitive_load = max(node.cognitive_load * decay_factor, floor)


# Singleton instance for ORB controller
hlsf_singleton = HLSFEngine(dimension=18)
