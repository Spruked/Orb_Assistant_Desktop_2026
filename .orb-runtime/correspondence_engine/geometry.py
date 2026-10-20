
"""
Correspondence Geometry — RESOLVED implementation.

Owns:
  weighted_euclidean_distance()      — implemented
  regularized_mahalanobis_distance() — implemented
  covariance_stability_check()       — RESOLVED: Frobenius norm \u0394S
  drift_velocity_check()             — RESOLVED: atom vector displacement
  MahalanobisGate                    — fully implemented
  correspondence_variance()          — RESOLVED: separate from entropy (GAP_D)

GAP_STABILITY RESOLVED: Frobenius norm of covariance matrix change.
GAP_DRIFT RESOLVED: Average atom vector displacement rate.
"""

import math
from dataclasses import dataclass
from typing import Dict, List, Optional

import numpy as np

from .vectors import CorrespondenceVector


def weighted_euclidean_distance(
    a: CorrespondenceVector,
    b: CorrespondenceVector,
    weights: Optional[Dict[str, float]] = None,
) -> float:
    dims = CorrespondenceVector.dimension_names()
    w = weights or {d: 1.0 for d in dims}
    total = 0.0
    for d in dims:
        diff = getattr(a, d) - getattr(b, d)
        total += w.get(d, 1.0) * (diff ** 2)
    return math.sqrt(total)


def regularized_mahalanobis_distance(
    a: CorrespondenceVector,
    b: CorrespondenceVector,
    inv_covariance: np.ndarray,
) -> float:
    va = np.array(a.as_tuple())
    vb = np.array(b.as_tuple())
    diff = (va - vb).reshape(-1, 1)
    dist_sq = float(diff.T @ inv_covariance @ diff)
    return math.sqrt(max(0.0, dist_sq))


def covariance_stability_check(vault, window: int, epsilon: float) -> bool:
    """
    RESOLVED (GAP_STABILITY): Frobenius norm of \u0394S across last K snapshots.
    """
    history = vault.covariance_history
    if len(history) < window + 1:
        return True

    recent = history[-window:]
    deltas = []
    for i in range(1, len(recent)):
        delta = recent[i] - recent[i-1]
        frob_norm = np.linalg.norm(delta, "fro")
        deltas.append(frob_norm)

    avg_delta = sum(deltas) / len(deltas)
    return avg_delta < epsilon


def drift_velocity_check(vault, window: int, max_velocity: float) -> bool:
    """
    RESOLVED (GAP_DRIFT): Average atom vector displacement over K cycles.
    """
    if len(vault.atoms) < 2:
        return True

    if not vault.atom_history or len(vault.atom_history) < window + 1:
        return True

    recent_history = vault.atom_history[-window:]
    total_displacement = 0.0
    count = 0

    for atom_id, atom in vault.atoms.items():
        vectors = []
        for snapshot in recent_history:
            if atom_id in snapshot:
                vectors.append(np.array(snapshot[atom_id].as_tuple()))

        if len(vectors) >= 2:
            for i in range(1, len(vectors)):
                displacement = np.linalg.norm(vectors[i] - vectors[i-1])
                total_displacement += displacement
                count += 1

    if count == 0:
        return True

    avg_velocity = total_displacement / count
    return avg_velocity < max_velocity


@dataclass
class MahalanobisGateConfig:
    min_claims_for_mahalanobis: int = 250
    engage_condition_number_max: float = 1e6
    release_condition_number_max: float = 1e8
    stability_window: int = 20
    stability_epsilon: float = 1e-3
    drift_window: int = 20
    drift_max_velocity: float = 0.1


class MahalanobisGate:
    def __init__(self, config: Optional[MahalanobisGateConfig] = None):
        self.config = config or MahalanobisGateConfig()
        self._engaged = False

    def _vault_maturity_passed(self, vault) -> bool:
        return len(vault.atoms) >= self.config.min_claims_for_mahalanobis

    def _condition_number_passed(self, covariance: np.ndarray) -> bool:
        cond = np.linalg.cond(covariance)
        threshold = (
            self.config.release_condition_number_max
            if self._engaged
            else self.config.engage_condition_number_max
        )
        return cond <= threshold

    def should_use_mahalanobis(self, vault) -> bool:
        if not self._vault_maturity_passed(vault):
            self._engaged = False
            return False

        covariance = vault.covariance_matrix()

        stable = covariance_stability_check(
            vault, self.config.stability_window, self.config.stability_epsilon
        )
        cond_ok = self._condition_number_passed(covariance)
        nonchaotic = drift_velocity_check(
            vault, self.config.drift_window, self.config.drift_max_velocity
        )

        self._engaged = stable and cond_ok and nonchaotic
        return self._engaged


def metric_selector_with_hysteresis(vault, gate: MahalanobisGate):
    if gate.should_use_mahalanobis(vault):
        cov = vault.covariance_matrix()
        inv_cov = np.linalg.pinv(cov)
        return "mahalanobis", inv_cov
    return "euclidean", None


def correspondence_variance(atom, neighbors: List) -> float:
    """
    GAP_D RESOLVED: Separate correspondence_variance signal.
    Computes variance across 5 correspondence dimensions.
    """
    if not neighbors:
        return 0.0

    dims = CorrespondenceVector.dimension_names()
    variances = []

    for dim in dims:
        neighbor_values = [getattr(n.correspondence_vector, dim) for n in neighbors]
        mean_val = sum(neighbor_values) / len(neighbor_values)
        variance = sum((v - mean_val) ** 2 for v in neighbor_values) / len(neighbor_values)
        variances.append(variance)

    return sum(variances) / len(variances)
