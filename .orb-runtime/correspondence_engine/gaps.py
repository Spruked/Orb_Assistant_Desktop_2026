
"""
Explicit registry of architectural questions.

STATUS: ALL CRITICAL GAPS RESOLVED. This file now serves as
documentation of what was resolved and how.
"""

# === RESOLVED GAPS ===

GAP_A_RESOLVED = """
GAP_A — RESOLVED by correspondence_substrate.py

The Correspondence Substrate now owns 5D correspondence vector
computation. It maps KnowledgeClaim + EvidenceItems -> CorrespondenceVector
using deterministic, bounded, auditable heuristics.

Resolution: Revived CS as standalone module between claims.py and atoms.py.
"""

GAP_C_RESOLVED = """
GAP_C — RESOLVED by beams.py

Beam circularity is now controlled by the CircularityGuard in
PhilosophicalBeam. A beam cannot reason over an atom produced from
its own prior output without independent validation.

Invariant enforced: A beam may not reinforce its own newly produced
atom until that atom passes independent validation or probation.
"""

GAP_D_RESOLVED = """
GAP_D — RESOLVED by fifth_mind.py

Fifth Mind is scoped to beam-disagreement entropy ONLY.
A SEPARATE signal, correspondence_variance, is computed by
geometry.correspondence_variance() for uncertainty across the 5
correspondence dimensions. These signals are NOT overloaded.
"""

GAP_ECM_RESOLVED = """
GAP_ECM — RESOLVED by escalation.py

Until ECM is built, all escalations go to EscalationQueue:
  - escalation_log (persistent audit trail)
  - human_review_queue (flagged for human attention)

No escalation is silently dropped. All are logged, timestamped,
and queued for review.
"""

GAP_F_RESOLVED = """
GAP_F — RESOLVED by claims.py + sublimator.py

KnowledgeClaim schema is now frozen:
  subject, predicate, object_, claim_text, evidence_ids,
  provenance, timestamp, confidence, degradation_signal,
  contradicts_claim_ids, caveats

Claim -> Atom promotion trigger: confidence >= 0.25 + correspondence
vector assigned by CorrespondenceSubstrate.
"""

GAP_STABILITY_RESOLVED = """
GAP_STABILITY — RESOLVED by geometry.py

covariance_stability_check now computes:
  Frobenius norm of \u0394S (change in covariance matrix) across last K
  vault updates, staying below epsilon.

Vault now retains covariance_history for this computation.
"""

GAP_DRIFT_RESOLVED = """
GAP_DRIFT — RESOLVED by geometry.py

drift_velocity_check now computes:
  Average KnowledgeAtom vector displacement over K vault cycles.

This is DISTINCT from covariance stability (which measures the
covariance matrix's rate of change, not individual atoms).
"""

GAP_FEEDBACK_RESOLVED = """
GAP_FEEDBACK — RESOLVED by challenge.py (AntifragileFeedback)

When a challenge succeeds, the system now:
  1. Corrects the atom (or removes it)
  2. Down-weights weak provenance (via substrate.provenance_reliability)
  3. Flags bad sublimation patterns (via pattern_risk_scores)
  4. Reduces future influence of similar unverified claims

This makes the system antifragile, not merely robust.
"""

GAP_PROBATION_RESOLVED = """
GAP_PROBATION — RESOLVED by atoms.py + vault.py + challenge.py

New atoms start probationary=True with:
  - Reduced influence weight on neighbors
  - Tighter re-challenge sensitivity (2x normal)
  - Shorter stale threshold (1/10 normal)

Atoms clear probation after surviving 3+ cycles without triggering
rechallenge conditions.
"""

# === OPEN GAPS (non-blocking) ===

GAP_HLSF_INTEGRATION = """
GAP_HLSF_INTEGRATION — HLSF is called via HLSFInterface plug-and-play.
The engine does not contain HLSF. Full integration requires external
HLSF instance to be passed at initialization.
"""

GAP_EGF_INTEGRATION = """
GAP_EGF_INTEGRATION — EGF is called via EGFInterface plug-and-play.
The engine does not contain EGF. Full integration requires external
EGF instance to be passed at initialization.
"""

GAP_ECM_BUILD = """
GAP_ECM_BUILD — EscalationQueue is the interim destination. Building
the actual ECM (Epistemic Convergence Matrix) remains future work.
"""

ALL_GAPS = [
    GAP_A_RESOLVED, GAP_C_RESOLVED, GAP_D_RESOLVED, GAP_ECM_RESOLVED,
    GAP_F_RESOLVED, GAP_STABILITY_RESOLVED, GAP_DRIFT_RESOLVED,
    GAP_FEEDBACK_RESOLVED, GAP_PROBATION_RESOLVED,
]
