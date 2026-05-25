import numpy as np
from typing import Dict, List, Any, Optional
from dataclasses import dataclass
import time
from collections import defaultdict, deque


@dataclass
class BayesianPrior:
    hypothesis: str
    prior_probability: float
    evidence_strength: float
    last_updated: float


@dataclass
class BayesianEvidence:
    evidence_id: str
    likelihood: float
    timestamp: float
    source: str
    reliability: float


class BayesianEngine:
    def __init__(self, alpha: float = 1.0, beta: float = 1.0):
        self.priors = {}
        self.evidence_history = defaultdict(list)
        self.alpha = alpha  # Prior success
        self.beta = beta  # Prior failure
        self.hypothesis_tracking = {}

    def set_prior(
        self, hypothesis: str, probability: float, evidence_strength: float = 1.0
    ):
        """Set prior probability for hypothesis"""
        self.priors[hypothesis] = BayesianPrior(
            hypothesis=hypothesis,
            prior_probability=probability,
            evidence_strength=evidence_strength,
            last_updated=time.time(),
        )

    def add_evidence(
        self,
        hypothesis: str,
        evidence_id: str,
        likelihood: float,
        source: str = "unknown",
        reliability: float = 1.0,
    ):
        """Add evidence for hypothesis"""
        evidence = BayesianEvidence(
            evidence_id=evidence_id,
            likelihood=likelihood,
            timestamp=time.time(),
            source=source,
            reliability=reliability,
        )

        self.evidence_history[hypothesis].append(evidence)

        # Update hypothesis tracking
        if hypothesis not in self.hypothesis_tracking:
            self.hypothesis_tracking[hypothesis] = {
                "success_count": 0,
                "total_count": 0,
                "recent_performance": deque(maxlen=100),
            }

    def calculate_posterior(self, hypothesis: str) -> Optional[float]:
        """Calculate posterior probability using Bayes' theorem"""
        if hypothesis not in self.priors:
            return None

        prior = self.priors[hypothesis]
        evidence_list = self.evidence_history[hypothesis]

        if not evidence_list:
            return prior.prior_probability

        # Calculate likelihood of all evidence
        total_likelihood = 1.0
        for evidence in evidence_list:
            # Weight by reliability and recency
            time_decay = self._calculate_time_decay(evidence.timestamp)
            weight = evidence.reliability * time_decay
            weighted_likelihood = evidence.likelihood * weight + (1 - weight) * 0.5
            total_likelihood *= weighted_likelihood

        # Normalize
        prior_prob = prior.prior_probability
        marginal_probability = prior_prob * total_likelihood + (1 - prior_prob) * (
            1 - total_likelihood
        )

        if marginal_probability == 0:
            return prior_prob

        posterior = (prior_prob * total_likelihood) / marginal_probability
        return min(1.0, max(0.0, posterior))

    def update_with_outcome(self, hypothesis: str, success: bool, weight: float = 1.0):
        """Update prior based on outcome"""
        if hypothesis not in self.hypothesis_tracking:
            return

        tracking = self.hypothesis_tracking[hypothesis]
        tracking["total_count"] += 1
        tracking["recent_performance"].append(1.0 if success else 0.0)

        if success:
            tracking["success_count"] += 1

        # Update prior using beta distribution
        success_rate = tracking["success_count"] / tracking["total_count"]
        recent_performance = (
            np.mean(tracking["recent_performance"])
            if tracking["recent_performance"]
            else 0.5
        )

        # Combine long-term and recent performance
        new_prior = 0.7 * success_rate + 0.3 * recent_performance

        if hypothesis in self.priors:
            # Smooth update
            current_prior = self.priors[hypothesis].prior_probability
            updated_prior = current_prior * (1 - weight) + new_prior * weight
            self.priors[hypothesis].prior_probability = updated_prior
            self.priors[hypothesis].last_updated = time.time()

    def _calculate_time_decay(
        self, evidence_timestamp: float, half_life: float = 24 * 3600
    ) -> float:
        """Calculate time decay factor for evidence"""
        current_time = time.time()
        time_diff = current_time - evidence_timestamp
        decay_factor = 0.5 ** (time_diff / half_life)
        return decay_factor

    def get_competing_hypotheses(
        self, evidence: Dict[str, float]
    ) -> List[Dict[str, Any]]:
        """Evaluate multiple hypotheses against same evidence"""
        results = []

        for hypothesis in self.priors:
            posterior = self.calculate_posterior(hypothesis)
            if posterior is not None:
                results.append(
                    {
                        "hypothesis": hypothesis,
                        "posterior_probability": posterior,
                        "prior_probability": self.priors[hypothesis].prior_probability,
                        "evidence_count": len(self.evidence_history[hypothesis]),
                    }
                )

        return sorted(results, key=lambda x: x["posterior_probability"], reverse=True)

    def get_evidence_summary(self, hypothesis: str) -> Dict[str, Any]:
        """Get summary of evidence for hypothesis"""
        if hypothesis not in self.evidence_history:
            return {}

        evidence_list = self.evidence_history[hypothesis]
        recent_evidence = [
            e for e in evidence_list if time.time() - e.timestamp < 7 * 24 * 3600
        ]

        return {
            "total_evidence": len(evidence_list),
            "recent_evidence": len(recent_evidence),
            "avg_likelihood": (
                np.mean([e.likelihood for e in evidence_list]) if evidence_list else 0
            ),
            "avg_reliability": (
                np.mean([e.reliability for e in evidence_list]) if evidence_list else 0
            ),
            "most_common_source": (
                max(
                    set([e.source for e in evidence_list]),
                    key=[e.source for e in evidence_list].count,
                )
                if evidence_list
                else "none"
            ),
        }
