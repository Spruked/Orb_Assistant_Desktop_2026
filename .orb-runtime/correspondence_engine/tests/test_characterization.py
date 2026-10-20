"""
Characterization tests: these pin CURRENT behavior so that changes are
deliberate. They do not endorse it. Each docstring names the open concern.
When a concern is resolved, update the matching test in the same change.

Run from the folder that contains the ``correspondence_engine`` package:

    python -B -m unittest discover -s correspondence_engine/tests -p "test_characterization.py"
"""

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from correspondence_engine import AUIEngine, EvidenceItem, RelationType


def evidence(claim, source="mon", confidence=0.85, degradation=0.2, **kwargs):
    return EvidenceItem(
        claim=claim,
        source=source,
        confidence=confidence,
        degradation_signal=degradation,
        timestamp=datetime.utcnow(),
        supports_dimension="reality",
        **kwargs,
    )


class AtomLifecycleCharacterization(unittest.TestCase):
    """Concern: irreversible deletion of isolated, otherwise valid knowledge."""

    def test_isolated_probationary_atom_below_0_7_is_deleted_on_first_cycle(self):
        engine = AUIEngine()
        atom = engine.ingest([evidence("The backup job finished successfully.", confidence=0.6, degradation=0.1)])
        engine.run_maintenance()
        self.assertNotIn(atom.atom_id, engine.vault.atoms)

    def test_isolated_atom_at_or_above_0_7_survives(self):
        engine = AUIEngine()
        atom = engine.ingest([evidence("The backup job finished successfully.", confidence=0.75, degradation=0.1)])
        for _ in range(5):
            engine.run_maintenance()
        self.assertIn(atom.atom_id, engine.vault.atoms)

    def test_deletion_penalizes_the_source_and_keeps_no_recoverable_record(self):
        engine = AUIEngine()
        atom = engine.ingest([evidence("The backup job finished successfully.", confidence=0.6, degradation=0.1)])
        engine.run_maintenance()
        self.assertAlmostEqual(engine.substrate.provenance_reliability["mon"], 0.4)
        record = engine.antifragile.correction_log[-1]
        self.assertEqual(record["atom_id"], atom.atom_id)
        self.assertNotIn("backup job", str(record))


class ContradictionCharacterization(unittest.TestCase):
    """Concern: opposing evidence may not become CONTRADICTS edges."""

    def test_opposed_claims_at_distance_0_65_create_no_edge(self):
        engine = AUIEngine()
        engine.ingest([evidence("The service is healthy.", confidence=0.9, degradation=0.05)])
        engine.ingest([evidence("The service is down.", source="pager", confidence=0.9, degradation=0.95)])
        self.assertEqual(engine.vault.edges, [])

    def test_explicit_contradicts_ids_do_not_create_a_contradiction_edge(self):
        engine = AUIEngine()
        engine.ingest([evidence("Door is locked.")])
        engine.ingest([evidence("Door is open.", contradicts=["claim_1"])])
        relations = [edge.relation for edge in engine.vault.edges]
        self.assertNotIn(RelationType.CONTRADICTS, relations)
        self.assertIn(RelationType.CORROBORATES, relations)


class AffirmCeilingCharacterization(unittest.TestCase):
    """Concern: unknown inputs default to 0.5 and are scored as if known."""

    def test_new_source_single_evidence_does_not_reach_affirm(self):
        engine = AUIEngine()
        atom = engine.ingest([evidence("The backup job finished successfully.", confidence=0.95, degradation=0.0)])
        self.assertEqual(engine.reason([atom]).final_verdict, "suspend")

    def test_affirm_needs_established_source_and_corroboration(self):
        engine = AUIEngine()
        for _ in range(10):
            engine.substrate.update_provenance_reliability("mon", "passed", 0.1)
        atom = engine.ingest([
            evidence("The backup job finished successfully.", confidence=0.95, degradation=0.0, corroboration_count=5)
        ])
        self.assertEqual(engine.reason([atom]).final_verdict, "affirm")

    def test_personhood_stays_neutral_without_keyword_evidence(self):
        engine = AUIEngine()
        atom = engine.ingest([evidence("The backup job finished successfully.", confidence=0.95, degradation=0.0)])
        self.assertEqual(atom.correspondence_vector.personhood, 0.5)


if __name__ == "__main__":
    unittest.main()
