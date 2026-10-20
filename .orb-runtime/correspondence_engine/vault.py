
"""
Vault — ENHANCED with covariance history, atom history, probation tracking.

Storage shape frozen. Now implements:
  - covariance_history for GAP_STABILITY
  - atom_history for GAP_DRIFT
  - probation tracking for GAP_PROBATION
  - Organized Doubt scheduling hooks
"""

from typing import Dict, List
from datetime import datetime
import numpy as np

from .atoms import KnowledgeAtom, CorrespondenceEdge


class Vault:
    def __init__(self):
        self.atoms: Dict[str, KnowledgeAtom] = {}
        self.edges: List[CorrespondenceEdge] = []
        self.covariance_history: List[np.ndarray] = []
        self.atom_history: List[Dict[str, "CorrespondenceVector"]] = []
        self.cycle_count: int = 0
        self.atom_validation_cycles: Dict[str, int] = {}

    def add_atom(self, atom: KnowledgeAtom):
        if atom.atom_id in self.atoms:
            raise ValueError(f"atom_id {atom.atom_id} already exists")
        self.atoms[atom.atom_id] = atom
        self.atom_validation_cycles[atom.atom_id] = self.cycle_count

    def add_edge(self, edge: CorrespondenceEdge):
        for atom_id in (edge.source_atom_id, edge.target_atom_id):
            if atom_id not in self.atoms:
                raise ValueError(f"edge references unknown atom_id {atom_id}")
        self.edges.append(edge)

    def edges_for(self, atom_id: str) -> List[CorrespondenceEdge]:
        return [
            e for e in self.edges
            if atom_id in (e.source_atom_id, e.target_atom_id)
        ]

    def covariance_matrix(self) -> np.ndarray:
        if len(self.atoms) < 2:
            raise ValueError("covariance_matrix requires at least 2 atoms")
        vectors = np.array([a.correspondence_vector.as_tuple() for a in self.atoms.values()])
        cov = np.cov(vectors, rowvar=False)
        self.covariance_history.append(cov.copy())
        if len(self.covariance_history) > 1000:
            self.covariance_history = self.covariance_history[-500:]
        return cov

    def snapshot_atom_vectors(self):
        """Store current atom vectors for drift velocity checks."""
        snapshot = {
            atom_id: atom.correspondence_vector
            for atom_id, atom in self.atoms.items()
        }
        self.atom_history.append(snapshot)
        if len(self.atom_history) > 1000:
            self.atom_history = self.atom_history[-500:]

    def get_neighbors(self, atom_id: str, max_distance: float = 0.5) -> List[KnowledgeAtom]:
        from .geometry import weighted_euclidean_distance

        if atom_id not in self.atoms:
            return []

        source = self.atoms[atom_id]
        neighbors = []
        for other_id, other in self.atoms.items():
            if other_id == atom_id:
                continue
            dist = weighted_euclidean_distance(source.correspondence_vector, other.correspondence_vector)
            if dist <= max_distance:
                neighbors.append(other)
        return neighbors

    def advance_cycle(self):
        """Advance the vault cycle counter and snapshot state."""
        self.cycle_count += 1
        self.snapshot_atom_vectors()

        from dataclasses import replace
        for atom_id, atom in list(self.atoms.items()):
            if atom.probationary:
                new_cycles = atom.cycles_survived + 1
                updated = replace(atom, cycles_survived=new_cycles)
                if new_cycles >= 3:
                    updated = replace(updated, probationary=False)
                self.atoms[atom_id] = updated

    def get_probationary_atoms(self) -> List[KnowledgeAtom]:
        return [a for a in self.atoms.values() if a.probationary]

    def get_stale_atoms(self, max_cycles: int = 500) -> List[KnowledgeAtom]:
        stale = []
        for atom_id, last_cycle in self.atom_validation_cycles.items():
            if self.cycle_count - last_cycle > max_cycles:
                if atom_id in self.atoms:
                    stale.append(self.atoms[atom_id])
        return stale
