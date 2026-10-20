"""
Regression tests for repaired defects.

Run from the folder that contains the ``correspondence_engine`` package:

    python -B -m unittest discover -s correspondence_engine/tests -p "test_regression.py"
"""

import sys
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from correspondence_engine import AUIEngine, CorrespondenceSubstrate, EvidenceItem, SemanticSublimator


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


class ProvenanceAccessorTests(unittest.TestCase):
    def test_public_accessor_matches_private_value(self):
        substrate = CorrespondenceSubstrate()
        self.assertEqual(substrate.get_provenance_reliability("never_seen"), 0.5)
        substrate.update_provenance_reliability("src", "passed", 0.1)
        self.assertAlmostEqual(substrate.get_provenance_reliability("src"), 0.6)
        self.assertEqual(
            substrate.get_provenance_reliability("src"),
            substrate._get_provenance_reliability("src"),
        )

    def test_understanding_window_does_not_crash(self):
        engine = AUIEngine()
        atom = engine.ingest([evidence("The system maintains stability under load.")])
        window = engine.get_understanding_window(atom.atom_id)
        self.assertIsNotNone(window)
        self.assertEqual(window["atom_id"], atom.atom_id)
        self.assertEqual(window["provenance_reliability"], 0.5)

    def test_unknown_atom_has_no_window(self):
        self.assertIsNone(AUIEngine().get_understanding_window("missing"))


class PredicateExtractionTests(unittest.TestCase):
    CASES = [
        ("The disk is full.", ("The disk", "is", "full")),
        ("The disk is a SSD.", ("The disk", "is", "SSD")),
        ("It does not start", ("It", "does not", "start")),
        ("The plan will be real", ("The plan", "will be", "real")),
        ("Heat causes expansion", ("Heat", "causes", "expansion")),
        ("Load leads to failure", ("Load", "leads to", "failure")),
        ("The service requires a restart", ("The service", "requires", "a restart")),
        ("The cache depends on the config", ("The cache", "depends on", "the config")),
        ("This equals that", ("This", "equals", "that")),
        ("The kit contains parts", ("The kit", "contains", "parts")),
    ]

    def setUp(self):
        self.sublimator = SemanticSublimator()

    def test_predicates_keep_the_stated_verb_phrase(self):
        for text, expected in self.CASES:
            with self.subTest(text=text):
                self.assertEqual(self.sublimator._extract_triple(text), expected)

    def test_predicate_never_contains_regex_syntax(self):
        for text, _ in self.CASES:
            _, predicate, _ = self.sublimator._extract_triple(text)
            for token in ("|", "\\", "(", ")", "?", "*", "+"):
                self.assertNotIn(token, predicate, msg=f"{text!r} -> {predicate!r}")

    def test_verb_does_not_split_a_longer_word(self):
        # "does nothing" used to become predicate "does not" + object "hing".
        self.assertEqual(
            self.sublimator._extract_triple("The cat does nothing"),
            ("The cat", "does", "nothing"),
        )
        # "causeway" is not the verb "causes"; the copula is the real predicate.
        subject, predicate, object_ = self.sublimator._extract_triple("The wind causeway is open")
        self.assertEqual((subject, predicate, object_), ("The wind causeway", "is", "open"))

    def test_explicit_markers_still_win(self):
        triple = self.sublimator._extract_triple("[Subject] A [Predicate] causes [Object] B")
        self.assertEqual(triple, ("A", "causes", "B"))

    def test_vague_copula_is_not_scored_as_specific(self):
        substrate = CorrespondenceSubstrate()
        _, predicate, _ = self.sublimator._extract_triple("The disk is full.")
        self.assertEqual(substrate._assess_predicate_specificity(predicate), 0.3)

    def test_trailing_sentence_punctuation_is_stripped_from_the_object(self):
        cases = [
            ("The disk is full.", "full"),
            ("Heat causes expansion!", "expansion"),
            ("The kit contains parts, tools;", "parts, tools"),
            ("The note says: Load leads to failure.. ", "failure"),
            ("[Subject] A [Predicate] causes [Object] B.", "B"),
            ("Hello world.", "world"),
            ("Hello world?!", "world"),
        ]
        for text, expected in cases:
            with self.subTest(text=text):
                self.assertEqual(self.sublimator._extract_triple(text)[2], expected)

    def test_punctuation_inside_the_object_is_preserved(self):
        self.assertEqual(self.sublimator._extract_triple("The file is v1.2.3.")[2], "v1.2.3")
        self.assertEqual(self.sublimator._extract_triple("The kit contains parts, tools.")[2], "parts, tools")
        self.assertEqual(self.sublimator._extract_triple("The ratio equals 3.5.")[2], "3.5")

    def test_only_the_object_is_modified_and_claim_text_stays_raw(self):
        subject, predicate, _ = self.sublimator._extract_triple("What. Heat causes expansion!")
        self.assertEqual((subject, predicate), ("What. Heat", "causes"))
        claim = self.sublimator.sublimate([evidence("The disk is full.")])
        self.assertEqual(claim.claim_text, "The disk is full.")
        self.assertEqual(claim.object_, "full")

    def test_object_precision_still_counts_a_stripped_object(self):
        substrate = CorrespondenceSubstrate()
        claim = self.sublimator.sublimate([evidence("The disk is full.")])
        raw = substrate._aggregate_evidence_signals([evidence("The disk is full.")], claim)
        self.assertEqual(raw["object_precision"], 0.7)

    def test_fallbacks_unchanged(self):
        self.assertEqual(self.sublimator._extract_triple("Hello world"), ("Hello", "is", "world"))
        self.assertEqual(self.sublimator._extract_triple("Hello"), ("Hello", "is", "unknown"))


if __name__ == "__main__":
    unittest.main()
