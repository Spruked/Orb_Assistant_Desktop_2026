
"""
AUI Engine — Artificial Understanding and Intelligence Engine.

The standalone, self-pruning, self-improving reasoning and understanding
engine that creates a window in the reasoning for machine understanding.

This is a NON-LLM AI. It uses structured knowledge graphs, geometric
correspondence, and philosophical beams to achieve understanding
through structure, not generation.

PLUG-AND-PLAY ARCHITECTURE:
  - Calls HLSF/EGF via interfaces (does not contain them)
  - Accepts EvidenceItems from any source
  - Outputs TribunalJudgments to any consumer
  - Self-prunes: trims old history, archives resolved escalations
  - Self-improves: learns from challenge results via antifragile feedback

PIPELINE:
  EvidenceItem
  \u2193
  Semantic Sublimator
  \u2193
  KnowledgeClaim
  \u2193
  Correspondence Substrate
  \u2193
  KnowledgeAtom
  \u2193
  Correspondence Geometry
  \u2193
  [HLSF / EGF — called via interface, not contained]
  \u2193
  TPC Beams
  \u2193
  Fifth Mind / Tribunal
  \u2193
  Escalation Queue (interim) / ECM (future)
"""

from typing import Dict, List, Optional, Callable, Any
from datetime import datetime

from .evidence import EvidenceItem
from .vectors import CorrespondenceVector
from .claims import KnowledgeClaim
from .atoms import KnowledgeAtom, CorrespondenceEdge, RelationType
from .sublimator import SemanticSublimator
from .correspondence_substrate import CorrespondenceSubstrate
from .vault import Vault
from . import geometry
from .beams import HumeBeam, KantBeam, LockeBeam, SpinozaBeam, BeamOutput
from .fifth_mind import FifthMind
from .tribunal import TribunalSynthesizer, TribunalJudgment
from .escalation import EscalationQueue
from .challenge import ReChallengeConfig, needs_rechallenge, AntifragileFeedback


class HLSFInterface:
    """Plug-and-play interface for HLSF (18D traversal, vivacity decay)."""

    def __init__(self, hlsf_instance=None):
        self.hlsf = hlsf_instance

    def place_atom(self, atom: KnowledgeAtom) -> dict:
        if self.hlsf:
            return self.hlsf.place(atom)
        return {"placed": True, "coordinates": atom.correspondence_vector.as_tuple()}

    def traverse(self, from_atom_id: str, direction: str) -> List[str]:
        if self.hlsf:
            return self.hlsf.traverse(from_atom_id, direction)
        return []


class EGFInterface:
    """Plug-and-play interface for EGF (certainty gravity retrieval)."""

    def __init__(self, egf_instance=None):
        self.egf = egf_instance

    def retrieve(
        self,
        query_vector: CorrespondenceVector,
        vault: Vault,
        combine_with_correspondence: bool = True,
    ) -> List[KnowledgeAtom]:
        if not self.egf:
            return self._correspondence_retrieval(query_vector, vault)

        results = []
        for atom in vault.atoms.values():
            gravity = 0.5  # default if egf cannot provide
            if hasattr(self.egf, "get_gravity"):
                gravity = self.egf.get_gravity(atom.atom_id)
            dist = geometry.weighted_euclidean_distance(query_vector, atom.correspondence_vector)
            correspondence_score = 1.0 / (1.0 + dist)
            combined = 0.6 * gravity + 0.4 * correspondence_score
            results.append((atom, combined))

        results.sort(key=lambda x: x[1], reverse=True)
        return [r[0] for r in results[:20]]

    def _correspondence_retrieval(
        self,
        query_vector: CorrespondenceVector,
        vault: Vault,
    ) -> List[KnowledgeAtom]:
        results = []
        for atom in vault.atoms.values():
            dist = geometry.weighted_euclidean_distance(query_vector, atom.correspondence_vector)
            results.append((atom, dist))
        results.sort(key=lambda x: x[1])
        return [r[0] for r in results[:20]]


class AUIEngine:
    """
    Artificial Understanding and Intelligence Engine.

    Self-pruning, self-improving, plug-and-play.
    """

    def __init__(
        self,
        hlsf_instance=None,
        egf_instance=None,
        rechallenge_config: Optional[ReChallengeConfig] = None,
    ):
        self.vault = Vault()
        self.sublimator = SemanticSublimator()
        self.substrate = CorrespondenceSubstrate()
        self.mahalanobis_gate = geometry.MahalanobisGate()

        self.beams = [
            HumeBeam(),
            KantBeam(),
            LockeBeam(),
            SpinozaBeam(),
        ]
        self.fifth_mind = FifthMind()
        self.tribunal = TribunalSynthesizer()

        self.escalation_queue = EscalationQueue()

        self.rechallenge_config = rechallenge_config or ReChallengeConfig()
        self.antifragile = AntifragileFeedback(self.substrate)

        self.hlsf = HLSFInterface(hlsf_instance)
        self.egf = EGFInterface(egf_instance)

        self.cycle: int = 0
        self.atom_counter: int = 0
        self.processing_log: List[dict] = []

        self.max_log_entries: int = 10000
        self.max_vault_size: int = 100000

    def ingest(self, evidence_items: List[EvidenceItem]) -> KnowledgeAtom:
        """Ingest evidence and produce a KnowledgeAtom."""
        claim = self.sublimator.sublimate(evidence_items)
        vector = self.substrate.compute_vector(claim, evidence_items)

        self.atom_counter += 1
        atom_id = f"atom_{self.atom_counter}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        atom = claim.promote_to_atom(vector, atom_id)

        self.vault.add_atom(atom)
        self.hlsf.place_atom(atom)
        self._establish_edges(atom, claim)

        self.processing_log.append({
            "cycle": self.cycle,
            "action": "ingest",
            "atom_id": atom.atom_id,
            "claim_id": claim.claim_id,
            "confidence": atom.confidence,
        })

        self._self_prune()
        return atom

    def _establish_edges(self, new_atom: KnowledgeAtom, claim: KnowledgeClaim):
        """Establish edges between new atom and existing atoms."""
        for existing_id, existing in self.vault.atoms.items():
            if existing_id == new_atom.atom_id:
                continue
            if claim.claim_id in existing.source_claim_id:
                continue

            dist = geometry.weighted_euclidean_distance(
                new_atom.correspondence_vector,
                existing.correspondence_vector,
            )

            if dist < 0.3:
                edge = CorrespondenceEdge(
                    source_atom_id=new_atom.atom_id,
                    target_atom_id=existing.atom_id,
                    relation=RelationType.CORROBORATES,
                    weight=1.0 - dist,
                    confidence=min(new_atom.confidence, existing.confidence),
                    timestamp=datetime.utcnow(),
                )
                self.vault.add_edge(edge)
            elif dist > 0.8 and new_atom.observation.split()[0] == existing.observation.split()[0]:
                edge = CorrespondenceEdge(
                    source_atom_id=new_atom.atom_id,
                    target_atom_id=existing.atom_id,
                    relation=RelationType.CONTRADICTS,
                    weight=dist,
                    confidence=min(new_atom.confidence, existing.confidence),
                    timestamp=datetime.utcnow(),
                )
                self.vault.add_edge(edge)

    def reason(self, query_atoms: List[KnowledgeAtom]) -> TribunalJudgment:
        """Run the full reasoning pipeline over a set of atoms."""
        context = {"cycle": self.cycle, "vault_size": len(self.vault.atoms)}

        beam_outputs = []
        for beam in self.beams:
            output = beam.reason(query_atoms, context)
            beam_outputs.append(output)

        correspondence_var = 0.0
        if query_atoms:
            neighbors = []
            for atom in query_atoms:
                neighbors.extend(self.vault.get_neighbors(atom.atom_id))
            if neighbors:
                correspondence_var = geometry.correspondence_variance(query_atoms[0], neighbors)

        fifth_output = self.fifth_mind.evaluate(beam_outputs, correspondence_var)
        judgment = self.tribunal.judge(beam_outputs, fifth_output)

        if judgment.action == "escalate_to_ecm":
            self.escalation_queue.escalate(
                source="TribunalSynthesizer",
                reason=judgment.reasoning,
                affected_atom_ids=[a.atom_id for a in query_atoms],
                beam_outputs=beam_outputs,
                fifth_mind_output={
                    "entropy": fifth_output.entropy,
                    "consensus": fifth_output.consensus,
                    "recommendation": fifth_output.recommendation,
                },
                tribunal_judgment={
                    "verdict": judgment.final_verdict,
                    "confidence": judgment.confidence,
                    "action": judgment.action,
                },
            )

        return judgment

    def run_maintenance(self):
        """Run Organized Doubt / re-challenge cycle."""
        self.cycle += 1
        self.vault.advance_cycle()

        for atom_id, atom in list(self.vault.atoms.items()):
            last_validated = self.vault.atom_validation_cycles.get(atom_id, 0)

            reasons = needs_rechallenge(
                atom, self.vault, self.rechallenge_config,
                self.cycle, last_validated,
            )

            if reasons:
                result = self._perform_rechallenge(atom, reasons)
                self.antifragile.process_challenge_result(
                    atom, self.vault, result["verdict"],
                    result.get("corrected_vector"),
                )

        self._self_prune()

        return {
            "cycle": self.cycle,
            "atoms_checked": len(self.vault.atoms),
            "escalations_pending": self.escalation_queue.pending_count,
        }

    def _perform_rechallenge(self, atom: KnowledgeAtom, reasons: List[str]) -> dict:
        """Perform rechallenge on an atom."""
        try:
            neighbors = self.vault.get_neighbors(atom.atom_id)

            if not neighbors and atom.probationary:
                return {"verdict": "removed"}

            if atom.confidence < 0.2:
                return {"verdict": "removed"}

            if neighbors:
                var = geometry.correspondence_variance(atom, neighbors)
                if var > 0.5:
                    dims = CorrespondenceVector.dimension_names()
                    avg_vals = {}
                    for dim in dims:
                        vals = [getattr(n.correspondence_vector, dim) for n in neighbors]
                        avg_vals[dim] = sum(vals) / len(vals)
                    corrected = CorrespondenceVector(**avg_vals)
                    return {"verdict": "corrected", "corrected_vector": corrected}

            return {"verdict": "validated"}

        except Exception as e:
            self.escalation_queue.escalate(
                source="ReChallenge",
                reason=f"Rechallenge failed for {atom.atom_id}: {str(e)}",
                affected_atom_ids=[atom.atom_id],
            )
            return {"verdict": "validated"}

    def retrieve(self, query_vector: CorrespondenceVector) -> List[KnowledgeAtom]:
        """Retrieve relevant atoms using EGF + correspondence distance."""
        return self.egf.retrieve(query_vector, self.vault)

    def query(self, evidence_items: List[EvidenceItem]) -> TribunalJudgment:
        """Full query pipeline: ingest evidence, reason, return judgment."""
        atom = self.ingest(evidence_items)
        related = self.retrieve(atom.correspondence_vector)
        all_atoms = [atom] + related[:5]
        return self.reason(all_atoms)

    def get_understanding_window(self, atom_id: str) -> Optional[dict]:
        """
        Return the "understanding window" for an atom.

        This is the core AUI feature: structured meaning in geometric space.
        """
        if atom_id not in self.vault.atoms:
            return None

        atom = self.vault.atoms[atom_id]
        neighbors = self.vault.get_neighbors(atom_id)
        edges = self.vault.edges_for(atom_id)

        understanding_depth = self._compute_understanding_depth(atom)

        return {
            "atom_id": atom_id,
            "observation": atom.observation,
            "correspondence_vector": {
                "reality": atom.correspondence_vector.reality,
                "representation": atom.correspondence_vector.representation,
                "purpose": atom.correspondence_vector.purpose,
                "personhood": atom.correspondence_vector.personhood,
                "continuity": atom.correspondence_vector.continuity,
            },
            "confidence": atom.confidence,
            "probationary": atom.probationary,
            "cycles_survived": atom.cycles_survived,
            "neighbor_count": len(neighbors),
            "edge_count": len(edges),
            "understanding_depth": understanding_depth,
            "corroboration": len([e for e in edges if e.relation == RelationType.CORROBORATES]),
            "contradictions": len([e for e in edges if e.relation == RelationType.CONTRADICTS]),
            "provenance_reliability": self.substrate.get_provenance_reliability(atom.provenance),
            "geometric_stability": self._assess_geometric_stability(atom, neighbors),
        }

    def _compute_understanding_depth(self, atom: KnowledgeAtom) -> int:
        """Compute K\u2070\u2192K\u00b9\u2192K\u00b2 depth recursion level."""
        depth = 0
        neighbors = self.vault.get_neighbors(atom.atom_id)
        if neighbors:
            depth = 1
            for n in neighbors:
                n_neighbors = self.vault.get_neighbors(n.atom_id)
                if any(nn.atom_id != atom.atom_id for nn in n_neighbors):
                    depth = 2
                    break
        return depth

    def _assess_geometric_stability(self, atom: KnowledgeAtom, neighbors: List[KnowledgeAtom]) -> str:
        if not neighbors:
            return "isolated"
        var = geometry.correspondence_variance(atom, neighbors)
        if var < 0.1:
            return "stable"
        elif var < 0.3:
            return "drifting"
        else:
            return "unstable"

    def _self_prune(self):
        if len(self.processing_log) > self.max_log_entries:
            self.processing_log = self.processing_log[-self.max_log_entries//2:]

        if len(self.vault.atoms) > self.max_vault_size:
            sorted_atoms = sorted(
                self.vault.atoms.items(),
                key=lambda x: (x[1].cycles_survived, x[1].confidence),
            )
            to_remove = len(sorted_atoms) - self.max_vault_size + 1000
            for atom_id, _ in sorted_atoms[:to_remove]:
                if atom_id in self.vault.atoms:
                    del self.vault.atoms[atom_id]

            self.vault.edges = [
                e for e in self.vault.edges
                if e.source_atom_id in self.vault.atoms
                and e.target_atom_id in self.vault.atoms
            ]

    def get_stats(self) -> dict:
        return {
            "cycle": self.cycle,
            "vault_atoms": len(self.vault.atoms),
            "vault_edges": len(self.vault.edges),
            "escalations_pending": self.escalation_queue.pending_count,
            "escalation_stats": self.escalation_queue.stats(),
            "fifth_mind_trend": self.fifth_mind.get_trend(),
            "sublimator_stats": self.sublimator.get_extraction_stats(),
            "provenance_reliability": dict(self.substrate.provenance_reliability),
            "pattern_risk_scores": dict(self.antifragile.sublimation_pattern_scores),
        }
