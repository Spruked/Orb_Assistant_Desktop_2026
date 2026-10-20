"""
Semantic Sublimator — EvidenceItem(s) -> KnowledgeClaim.

MANDATORY scope, RESOLVED implementation.

Frozen responsibility: normalize irregular evidence into structured
claims, preserve contradictions, attach provenance. Nothing more.
Explicitly OUT of scope for this module:
  - correspondence vector computation (owned by correspondence_substrate.py)
  - distance metrics / geometric placement (owned by geometry.py)
  - Mahalanobis / metric selection (owned by geometry.py)

GAP_F RESOLVED: Extraction rules for subject/predicate/object are
now implemented. The rules are deterministic, bounded, and auditable.
This is NOT an LLM — it uses pattern matching and heuristics.
"""

import re
from typing import List, Optional
from datetime import datetime

from .evidence import EvidenceItem
from .claims import KnowledgeClaim


class SemanticSublimator:
    """
    Converts irregular evidence text into structured KnowledgeClaims.

    Extraction strategy (deterministic, non-LLM):
    1. Identify subject: noun phrase at start or after "[Subject]"
    2. Identify predicate: verb phrase connecting subject to object
    3. Identify object: noun phrase after predicate or "[Object]"
    4. Preserve full claim_text for semantic preservation
    5. Aggregate confidence and degradation from evidence
    """

    # Common predicate patterns (verb forms)
    _PREDICATE_PATTERNS = [
        r"is\s+(?:a|an|the)?\s*",           # "is a", "is the"
        r"has\s+(?:a|an|the)?\s*",          # "has a", "has the"
        r"does(?:\s+not)?\s*",              # "does", "does not"
        r"was\s+(?:a|an|the)?\s*",          # "was a"
        r"will\s+(?:be|have|do)\s*",        # "will be"
        r"can\s+(?:be|have|do)\s*",         # "can be"
        r"should\s+(?:be|have|do)\s*",      # "should be"
        r"must\s+(?:be|have|do)\s*",        # "must be"
        r"(?:causes?|leads?\s+to|results?\s+in)\s*",  # causal
        r"(?:requires?|needs?|depends?\s+on)\s*",     # dependency
        r"(?:equals?|is\s+equal\s+to|matches?)\s*",   # equality
        r"(?:contains?|includes?|comprises?)\s*",      # containment
        r"(?:affects?|influences?|impacts?)\s*",       # influence
        r"(?:creates?|generates?|produces?)\s*",       # creation
        r"(?:destroys?|removes?|eliminates?)\s*",      # destruction
    ]

    def __init__(self, claim_counter: int = 0):
        self.claim_counter = claim_counter
        self.extraction_log: List[dict] = []

    def sublimate(self, evidence_items: List[EvidenceItem]) -> KnowledgeClaim:
        """
        Convert one or more corroborating/conflicting EvidenceItems
        into a single structured KnowledgeClaim.

        RESOLVED: Extraction logic is now implemented using deterministic
        pattern matching, not LLM generation.
        """
        if not evidence_items:
            raise ValueError("cannot sublimate an empty evidence set")

        # Use the first (primary) evidence item for structure
        primary = evidence_items[0]
        claim_text = primary.claim

        # Extract subject, predicate, object
        subject, predicate, object_ = self._extract_triple(claim_text)

        # Aggregate confidence and degradation
        total_weight = sum(e.weight for e in evidence_items)
        if total_weight == 0:
            total_weight = 1.0

        aggregated_confidence = sum(
            e.effective_confidence() * e.weight for e in evidence_items
        ) / total_weight

        aggregated_degradation = sum(
            e.degradation_signal * e.weight for e in evidence_items
        ) / total_weight

        # Collect contradictions
        contradicts_ids = []
        for e in evidence_items:
            contradicts_ids.extend(e.contradicts)

        # Collect caveats
        caveats = []
        for e in evidence_items:
            caveats.extend(e.caveats)

        self.claim_counter += 1
        claim_id = f"claim_{self.claim_counter}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"

        claim = KnowledgeClaim(
            claim_id=claim_id,
            subject=subject,
            predicate=predicate,
            object_=object_,
            claim_text=claim_text,
            evidence_ids=[e.claim for e in evidence_items],  # Using claim text as evidence ID for now
            provenance=primary.source,
            timestamp=datetime.utcnow(),
            confidence=aggregated_confidence,
            degradation_signal=aggregated_degradation,
            contradicts_claim_ids=list(set(contradicts_ids)),
            caveats=list(set(caveats)),
        )

        # Log extraction for audit
        self.extraction_log.append({
            "claim_id": claim_id,
            "original_text": claim_text,
            "extracted_subject": subject,
            "extracted_predicate": predicate,
            "extracted_object": object_,
            "evidence_count": len(evidence_items),
            "confidence": aggregated_confidence,
        })

        return claim

    # Sentence punctuation that ends a statement but is not part of its object.
    _OBJECT_TRAILING_PUNCTUATION = " \t\r\n.,;:!?"

    def _extract_triple(self, text: str) -> tuple:
        """
        Extract (subject, predicate, object) and strip trailing sentence
        punctuation from the object only. ``claim_text`` keeps the raw
        statement, so no wording is lost; punctuation inside the object
        ("v1.2.3", "parts, tools") is preserved.
        """
        subject, predicate, object_ = self._split_triple(text)
        return subject, predicate, object_.rstrip(self._OBJECT_TRAILING_PUNCTUATION)

    def _split_triple(self, text: str) -> tuple:
        """
        Extract subject-predicate-object triple from claim text.

        Strategy:
        1. Look for explicit markers [Subject]...[Predicate]...[Object]
        2. If no markers, use pattern matching on sentence structure
        3. Fallback: first noun phrase = subject, first verb = predicate, remainder = object
        """
        text = text.strip()

        # Strategy 1: Explicit markers
        subject_match = re.search(r"\[Subject\]\s*([^\[]+)", text, re.IGNORECASE)
        predicate_match = re.search(r"\[Predicate\]\s*([^\[]+)", text, re.IGNORECASE)
        object_match = re.search(r"\[Object\]\s*([^\[]+)", text, re.IGNORECASE)

        if subject_match and predicate_match and object_match:
            return (
                subject_match.group(1).strip(),
                predicate_match.group(1).strip(),
                object_match.group(1).strip(),
            )

        # Strategy 2: Pattern matching on sentence structure
        # Try to find "X is Y" or "X has Y" patterns
        for pattern in self._PREDICATE_PATTERNS:
            # Capture the text the pattern actually matched, so the predicate
            # is the verb phrase as written ("causes", "leads to"), not the
            # regular expression itself. ``\b`` keeps a verb from splitting a
            # longer word ("does nothing" must not become "does not" + "hing").
            match = re.search(
                rf"^(.+?)\s+({pattern})\b\s*(.+)$", text, re.IGNORECASE
            )
            if match:
                subject = match.group(1).strip()
                predicate = re.sub(r"\s+", " ", match.group(2)).strip()
                # Copula + article ("is a", "has the") keeps the verb only.
                # The article is dropped from the triple (it was also dropped
                # from the object before this change); claim_text keeps it.
                predicate = re.sub(
                    r"^(is|has|was)\s+(?:a|an|the)$", r"\1", predicate, flags=re.IGNORECASE
                ) or "is"
                object_ = match.group(3).strip()
                return (subject, predicate, object_)

        # Strategy 3: Fallback — simple splitting
        words = text.split()
        if len(words) >= 3:
            # Find first verb-like word as predicate
            for i, word in enumerate(words[1:], 1):
                if word.lower() in {
                    "is", "has", "does", "was", "will", "can", "should", "must",
                    "causes", "leads", "requires", "equals", "contains", "affects",
                    "creates", "destroys", "produces", "results", "depends",
                }:
                    subject = " ".join(words[:i])
                    predicate = word
                    object_ = " ".join(words[i+1:])
                    return (subject, predicate, object_)

        # Ultimate fallback
        if len(words) >= 2:
            return (words[0], "is", " ".join(words[1:]))
        return (text, "is", "unknown")

    def get_extraction_stats(self) -> dict:
        """Return statistics about extractions for quality monitoring."""
        if not self.extraction_log:
            return {"total": 0, "avg_confidence": 0.0}
        return {
            "total": len(self.extraction_log),
            "avg_confidence": sum(e["confidence"] for e in self.extraction_log) / len(self.extraction_log),
            "recent_extractions": self.extraction_log[-5:],
        }
