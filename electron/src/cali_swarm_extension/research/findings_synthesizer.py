"""
findings_synthesizer.py

Findings Synthesizer
Compiles orb returns into coherent, defensible research reports.
Performs epistemic grading, uncertainty quantification, and
structured output generation.

Part of: CALI-Swarm_Extension / research/
"""

import json
import logging
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Set, Tuple, Any
from datetime import datetime
from enum import Enum
from collections import defaultdict
import re
import hashlib

from epistemic_swarm_governor_skg import (
    ResearchFinding, 
    ExtractedClaim,
    FindingStatus,
    SwarmMission,
    OrbInstance,
    OrbClass
)

logger = logging.getLogger("FindingsSynthesizer")


# ============================================================================
# SYNTHESIS OUTPUT STRUCTURES
# ============================================================================

class ConfidenceLevel(Enum):
    """Graded confidence for synthesis outputs"""
    VERIFIED = "verified"           # Multiple corroborating primary sources
    HIGHLY_PROBABLE = "highly_probable"  # Strong evidence, minor gaps
    PROBABLE = "probable"           # Good evidence, some uncertainty
    POSSIBLE = "possible"           # Weak evidence, significant uncertainty
    UNVERIFIED = "unverified"       # Single source or unverified claim
    DISPUTED = "disputed"           # Conflicting evidence
    SPECULATIVE = "speculative"     # Inference, no direct evidence

@dataclass
class SynthesizedClaim:
    """A claim with full epistemic provenance"""
    claim_id: str
    text: str
    confidence: ConfidenceLevel
    confidence_score: float  # 0.0-1.0 numeric
    
    # Provenance
    supporting_sources: List[Dict] = field(default_factory=list)
    contradicting_sources: List[Dict] = field(default_factory=list)
    primary_source_count: int = 0
    secondary_source_count: int = 0
    
    # Context
    entities_involved: List[str] = field(default_factory=list)
    temporal_context: Optional[str] = None  # When this claim applies
    geographic_context: Optional[str] = None  # Where applicable
    
    # Uncertainty
    gaps: List[str] = field(default_factory=list)  # What's missing
    caveats: List[str] = field(default_factory=list)  # Limitations
    
    def to_dict(self) -> Dict:
        return {
            'claim_id': self.claim_id,
            'text': self.text,
            'confidence': self.confidence.value,
            'confidence_score': round(self.confidence_score, 3),
            'source_breakdown': {
                'primary': self.primary_source_count,
                'secondary': self.secondary_source_count,
                'supporting': len(self.supporting_sources),
                'contradicting': len(self.contradicting_sources)
            },
            'entities': self.entities_involved,
            'context': {
                'temporal': self.temporal_context,
                'geographic': self.geographic_context
            },
            'uncertainty': {
                'gaps': self.gaps,
                'caveats': self.caveats
            }
        }

@dataclass
class EntityProfile:
    """Comprehensive profile of a discovered entity"""
    entity_id: str
    name: str
    entity_type: str  # person, organization, location, product, event, etc.
    
    # Descriptions from sources
    descriptions: List[Dict] = field(default_factory=list)  # [{text, source, confidence}]
    
    # Relationships
    relationships: List[Dict] = field(default_factory=list)
    # [{type, target_entity, evidence, confidence}]
    
    # Temporal
    first_mentioned: Optional[datetime] = None
    last_mentioned: Optional[datetime] = None
    active_periods: List[Dict] = field(default_factory=list)
    
    # Epistemic
    mention_count: int = 0
    source_diversity: int = 0  # Number of unique sources
    confidence_trend: List[float] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        # Select best description
        best_desc = max(self.descriptions, 
                       key=lambda d: d.get('confidence', 0)) if self.descriptions else {}
        
        return {
            'entity_id': self.entity_id,
            'name': self.name,
            'type': self.entity_type,
            'description': best_desc.get('text', 'No description available'),
            'description_source': best_desc.get('source', 'unknown'),
            'mention_count': self.mention_count,
            'source_diversity': self.source_diversity,
            'confidence': round(sum(self.confidence_trend) / 
                              max(len(self.confidence_trend), 1), 3),
            'relationships': [
                {
                    'type': r['type'],
                    'target': r['target_entity'],
                    'confidence': r['confidence']
                } for r in self.relationships[:10]  # Top 10
            ],
            'active_periods': self.active_periods
        }

@dataclass
class TimelineEvent:
    """Event with temporal placement"""
    event_id: str
    description: str
    date: Optional[datetime] = None
    date_precision: str = "unknown"  # exact, month, year, approximate
    confidence: ConfidenceLevel = ConfidenceLevel.UNVERIFIED
    
    # Source linkage
    supporting_findings: List[str] = field(default_factory=list)
    
    # Context
    entities_involved: List[str] = field(default_factory=list)
    preceding_events: List[str] = field(default_factory=list)
    following_events: List[str] = field(default_factory=list)

@dataclass
class ContradictionRecord:
    """Documented conflict in findings"""
    contradiction_id: str
    description: str
    severity: str  # low, medium, high, critical
    
    # Positions
    position_a: Dict  # {claims: [], sources: [], summary: ''}
    position_b: Dict
    
    # Resolution
    resolution_status: str = "unresolved"  # unresolved, partial, resolved
    resolution_notes: str = ""
    recommended_action: str = ""

@dataclass
class ResearchReport:
    """Complete synthesized research output"""
    report_id: str
    mission_id: str
    topic: str
    generated_at: datetime = field(default_factory=datetime.now)
    
    # Executive summary
    executive_summary: str = ""
    key_takeaways: List[str] = field(default_factory=list)
    
    # Epistemic overview
    overall_confidence: ConfidenceLevel = ConfidenceLevel.UNVERIFIED
    confidence_distribution: Dict[str, int] = field(default_factory=dict)
    
    # Core content
    verified_claims: List[SynthesizedClaim] = field(default_factory=list)
    disputed_claims: List[SynthesizedClaim] = field(default_factory=list)
    open_questions: List[str] = field(default_factory=list)
    
    # Structured data
    entity_profiles: Dict[str, EntityProfile] = field(default_factory=dict)
    timeline: List[TimelineEvent] = field(default_factory=list)
    contradictions: List[ContradictionRecord] = field(default_factory=list)
    
    # Source analysis
    sources_by_tier: Dict[str, List[Dict]] = field(default_factory=dict)
    source_gap_analysis: List[str] = field(default_factory=list)
    
    # Recommendations
    next_steps: List[str] = field(default_factory=list)
    recommended_verification: List[str] = field(default_factory=list)
    suggested_followup: List[str] = field(default_factory=list)
    
    # Metadata
    synthesis_stats: Dict = field(default_factory=dict)
    
    def to_dict(self) -> Dict:
        """Full serialization"""
        return {
            'report_id': self.report_id,
            'mission_id': self.mission_id,
            'topic': self.topic,
            'generated_at': self.generated_at.isoformat(),
            
            'executive_summary': self.executive_summary,
            'key_takeaways': self.key_takeaways,
            
            'epistemic_assessment': {
                'overall_confidence': self.overall_confidence.value,
                'confidence_distribution': self.confidence_distribution,
                'claim_breakdown': {
                    'verified': len([c for c in self.verified_claims 
                                   if c.confidence == ConfidenceLevel.VERIFIED]),
                    'highly_probable': len([c for c in self.verified_claims 
                                          if c.confidence == ConfidenceLevel.HIGHLY_PROBABLE]),
                    'probable': len([c for c in self.verified_claims 
                                   if c.confidence == ConfidenceLevel.PROBABLE]),
                    'disputed': len(self.disputed_claims),
                    'unverified': len([c for c in self.verified_claims 
                                     if c.confidence == ConfidenceLevel.UNVERIFIED])
                }
            },
            
            'claims': {
                'verified': [c.to_dict() for c in self.verified_claims[:20]],  # Top 20
                'disputed': [c.to_dict() for c in self.disputed_claims]
            },
            
            'entities': {
                k: v.to_dict() for k, v in list(self.entity_profiles.items())[:15]  # Top 15
            },
            
            'timeline': [
                {
                    'date': e.date.isoformat() if e.date else None,
                    'precision': e.date_precision,
                    'description': e.description,
                    'confidence': e.confidence.value
                } for e in sorted(self.timeline, 
                                  key=lambda x: x.date or datetime.min)[:50]  # Top 50
            ],
            
            'contradictions': [
                {
                    'description': c.description,
                    'severity': c.severity,
                    'status': c.resolution_status
                } for c in self.contradictions
            ],
            
            'sources': self.sources_by_tier,
            'gaps': self.source_gap_analysis,
            
            'recommendations': {
                'next_steps': self.next_steps,
                'verification_needed': self.recommended_verification,
                'followup_research': self.suggested_followup
            },
            
            'stats': self.synthesis_stats
        }
    
    def to_markdown(self) -> str:
        """Human-readable markdown format"""
        lines = [
            f"# Research Report: {self.topic}",
            "",
            f"**Report ID:** {self.report_id}  ",
            f"**Generated:** {self.generated_at.strftime('%Y-%m-%d %H:%M')}  ",
            f"**Overall Confidence:** {self.overall_confidence.value.upper()}",
            "",
            "## Executive Summary",
            "",
            self.executive_summary,
            "",
            "## Key Takeaways",
            ""
        ]
        
        for i, takeaway in enumerate(self.key_takeaways, 1):
            lines.append(f"{i}. {takeaway}")
        
        lines.extend([
            "",
            "## Verified Claims",
            ""
        ])
        
        for claim in self.verified_claims[:10]:
            lines.append(f"### {claim.confidence.value.upper()}: {claim.text[:100]}...")
            lines.append(f"- **Confidence Score:** {claim.confidence_score:.2f}")
            lines.append(f"- **Sources:** {claim.primary_source_count} primary, "
                        f"{claim.secondary_source_count} secondary")
            if claim.caveats:
                lines.append(f"- **Caveats:** {', '.join(claim.caveats)}")
            lines.append("")
        
        if self.disputed_claims:
            lines.extend([
                "## Disputed Claims",
                ""
            ])
            for claim in self.disputed_claims[:5]:
                lines.append(f"- **{claim.confidence.value.upper()}:** {claim.text[:80]}...")
        
        lines.extend([
            "",
            "## Key Entities",
            ""
        ])
        
        for entity in list(self.entity_profiles.values())[:10]:
            lines.append(f"### {entity.name} ({entity.entity_type})")
            lines.append(f"- Mentioned {entity.mention_count} times across "
                        f"{entity.source_diversity} sources")
            if entity.relationships:
                rel_summary = ", ".join(
                    f"{r['type']} {r['target_entity']}" for r in entity.relationships[:3]
                )
                lines.append(f"- Key relationships: {rel_summary}")
            lines.append("")
        
        lines.extend([
            "## Open Questions & Next Steps",
            ""
        ])
        
        for q in self.open_questions[:5]:
            lines.append(f"- ❓ {q}")
        
        for step in self.next_steps[:5]:
            lines.append(f"- ➡️  {step}")
        
        return "\n".join(lines)


# ============================================================================
# SYNTHESIS ENGINE
# ============================================================================

class SynthesisEngine:
    """
    Core synthesis logic for compiling findings into reports.
    """
    
    # Confidence scoring thresholds
    CONFIDENCE_THRESHOLDS = {
        ConfidenceLevel.VERIFIED: (0.90, 1.0),
        ConfidenceLevel.HIGHLY_PROBABLE: (0.75, 0.90),
        ConfidenceLevel.PROBABLE: (0.60, 0.75),
        ConfidenceLevel.POSSIBLE: (0.40, 0.60),
        ConfidenceLevel.UNVERIFIED: (0.20, 0.40),
        ConfidenceLevel.DISPUTED: (0.0, 1.0),  # Special handling
        ConfidenceLevel.SPECULATIVE: (0.0, 0.20)
    }
    
    # Source tier definitions
    SOURCE_TIERS = {
        'tier_1_primary': [
            'government_filing', 'court_record', 'official_statement',
            'sec_filing', 'patent_office', 'primary_interview'
        ],
        'tier_2_official': [
            'company_press_release', 'verified_news', 'industry_report',
            'academic_paper', 'expert_analysis'
        ],
        'tier_3_secondary': [
            'news_article', 'blog_post', 'podcast', 'review'
        ],
        'tier_4_unverified': [
            'social_media', 'forum_post', 'unverified_claim'
        ]
    }
    
    def __init__(self):
        self.synthesis_count = 0
    
    def synthesize(self,
                   findings: List[ResearchFinding],
                   mission: SwarmMission,
                   orbs: List[OrbInstance]) -> ResearchReport:
        """
        Main synthesis pipeline.
        """
        self.synthesis_count += 1
        report_id = f"synth_{mission.mission_id}_{self.synthesis_count}"
        
        logger.info(f"Starting synthesis {report_id} for {len(findings)} findings")
        
        report = ResearchReport(
            report_id=report_id,
            mission_id=mission.mission_id,
            topic=mission.topic
        )
        
        # Phase 1: Source analysis and tiering
        self._analyze_sources(findings, report)
        
        # Phase 2: Entity extraction and profiling
        self._build_entity_profiles(findings, report)
        
        # Phase 3: Claim extraction and consolidation
        self._consolidate_claims(findings, report)
        
        # Phase 4: Contradiction detection and documentation
        self._document_contradictions(findings, report)
        
        # Phase 5: Timeline construction
        self._build_timeline(findings, report)
        
        # Phase 6: Confidence grading
        self._grade_confidence(report)
        
        # Phase 7: Gap analysis and recommendations
        self._analyze_gaps(findings, report, mission)
        
        # Phase 8: Executive summary generation
        self._generate_executive_summary(report, mission)
        
        # Record stats
        report.synthesis_stats = {
            'findings_processed': len(findings),
            'unique_sources': len(set(f.source_reference for f in findings)),
            'entities_identified': len(report.entity_profiles),
            'claims_synthesized': len(report.verified_claims) + len(report.disputed_claims),
            'contradictions_found': len(report.contradictions),
            'timeline_events': len(report.timeline)
        }
        
        logger.info(f"Synthesis {report_id} complete: {report.synthesis_stats}")
        
        return report
    
    # =====================================================================
    # PHASE 1: Source Analysis
    # =====================================================================
    
    def _analyze_sources(self, findings: List[ResearchFinding], report: ResearchReport):
        """Categorize and analyze all sources"""
        tiered_sources = defaultdict(list)
        
        for finding in findings:
            source_type = finding.source_type
            source_ref = finding.source_reference
            
            # Determine tier
            tier = self._determine_source_tier(source_type)
            
            source_record = {
                'reference': source_ref,
                'type': source_type,
                'title': finding.source_title or 'Untitled',
                'date': finding.source_date.isoformat() if finding.source_date else None,
                'confidence': finding.confidence_score,
                'finding_count': 1  # Would aggregate
            }
            
            tiered_sources[tier].append(source_record)
        
        report.sources_by_tier = dict(tiered_sources)
        
        # Identify source gaps
        gaps = []
        if len(tiered_sources.get('tier_1_primary', [])) == 0:
            gaps.append("No primary source documents identified")
        if len(tiered_sources.get('tier_2_official', [])) < 2:
            gaps.append("Limited official source coverage")
        
        report.source_gap_analysis = list(gaps)
    
    def _determine_source_tier(self, source_type: str) -> str:
        """Map source type to reliability tier"""
        for tier, types in self.SOURCE_TIERS.items():
            if source_type in types:
                return tier
        return 'tier_4_unverified'
    
    # =====================================================================
    # PHASE 2: Entity Profiling
    # =====================================================================
    
    def _build_entity_profiles(self, findings: List[ResearchFinding], report: ResearchReport):
        """Build comprehensive profiles for all entities"""
        entity_data = defaultdict(lambda: {
            'mentions': [],
            'descriptions': [],
            'relationships': [],
            'dates': [],
            'sources': set()
        })
        
        for finding in findings:
            for entity in finding.entities_mentioned:
                entity_data[entity]['mentions'].append(finding)
                entity_data[entity]['sources'].add(finding.source_reference)
                
                # Extract description context
                desc = self._extract_entity_description(entity, finding.raw_content)
                if desc:
                    entity_data[entity]['descriptions'].append({
                        'text': desc,
                        'source': finding.source_reference,
                        'confidence': finding.confidence_score
                    })
                
                # Extract dates
                if finding.source_date:
                    entity_data[entity]['dates'].append(finding.source_date)
        
        # Create profiles
        for entity_name, data in entity_data.items():
            entity_id = f"ent_{hashlib.md5(entity_name.encode()).hexdigest()[:8]}"
            
            # Infer type from context
            entity_type = self._infer_entity_type(entity_name, data)
            
            # Determine active periods
            dates = sorted(data['dates'])
            active_periods = []
            if len(dates) >= 2:
                active_periods.append({
                    'start': dates[0].isoformat(),
                    'end': dates[-1].isoformat()
                })
            
            profile = EntityProfile(
                entity_id=entity_id,
                name=entity_name,
                entity_type=entity_type,
                descriptions=data['descriptions'],
                mention_count=len(data['mentions']),
                source_diversity=len(data['sources']),
                first_mentioned=dates[0] if dates else None,
                last_mentioned=dates[-1] if dates else None,
                active_periods=active_periods,
                confidence_trend=[m.confidence_score for m in data['mentions']]
            )
            
            report.entity_profiles[entity_id] = profile
        
        # Second pass: Build relationships
        self._infer_relationships(findings, report)
    
    def _extract_entity_description(self, entity: str, text: str) -> Optional[str]:
        """Extract sentence describing entity from context"""
        sentences = re.split(r'[.!?]+', text)
        for sent in sentences:
            if entity in sent and len(sent) > 20:
                return sent.strip()[:200]
        return None
    
    def _infer_entity_type(self, entity: str, data: Dict) -> str:
        """Infer whether entity is person, org, location, etc."""
        # Simple heuristics
        if any('CEO' in str(d) or 'President' in str(d) or 'founded by' in str(d) 
               for d in data['descriptions']):
            return 'person'
        
        if any('Inc' in entity or 'Corp' in entity or 'Company' in entity or 
               'LLC' in entity or 'Ltd' in entity):
            return 'organization'
        
        if any('acquired' in str(d) or 'merger' in str(d) 
               for d in data['descriptions']):
            return 'organization'
        
        # Default
        return 'unknown'
    
    def _infer_relationships(self, findings: List[ResearchFinding], report: ResearchReport):
        """Infer relationships between entities from co-occurrence"""
        # Simple co-occurrence analysis
        cooccurrence = defaultdict(lambda: defaultdict(int))
        
        for finding in findings:
            entities = finding.entities_mentioned
            for i, e1 in enumerate(entities):
                ent1_id = self._get_entity_id(e1, report)
                for e2 in entities[i+1:]:
                    ent2_id = self._get_entity_id(e2, report)
                    if ent1_id and ent2_id:
                        cooccurrence[ent1_id][ent2_id] += 1
                        cooccurrence[ent2_id][ent1_id] += 1
        
        # Add top relationships to profiles
        for ent_id, related in cooccurrence.items():
            if ent_id not in report.entity_profiles:
                continue
            
            top_related = sorted(related.items(), key=lambda x: x[1], reverse=True)[:5]
            
            for related_id, strength in top_related:
                rel_type = self._classify_relationship(
                    report.entity_profiles[ent_id],
                    report.entity_profiles.get(related_id),
                    findings
                )
                
                report.entity_profiles[ent_id].relationships.append({
                    'type': rel_type,
                    'target_entity': report.entity_profiles[related_id].name 
                                     if related_id in report.entity_profiles else related_id,
                    'evidence_strength': strength,
                    'confidence': min(0.7, 0.3 + strength * 0.1)
                })
    
    def _get_entity_id(self, entity_name: str, report: ResearchReport) -> Optional[str]:
        """Look up entity ID by name"""
        for eid, profile in report.entity_profiles.items():
            if profile.name == entity_name:
                return eid
        return None
    
    def _classify_relationship(self, 
                              entity_a: EntityProfile, 
                              entity_b: Optional[EntityProfile],
                              findings: List[ResearchFinding]) -> str:
        """Classify the type of relationship between entities"""
        # Simple classification based on context
        if not entity_b:
            return 'associated_with'
        
        # Check for acquisition language
        for finding in findings:
            text = finding.raw_content.lower()
            if (entity_a.name.lower() in text and entity_b.name.lower() in text):
                if any(word in text for word in ['acquired', 'acquisition', 'bought', 'purchased']):
                    return 'acquired_by' if 'acquired by' in text else 'acquired'
                if any(word in text for word in ['founded', 'founder', 'started']):
                    return 'founded_by'
                if any(word in text for word in ['partner', 'partnership', 'alliance']):
                    return 'partner'
                if any(word in text for word in ['competitor', 'rival', 'competing']):
                    return 'competitor'
        
        return 'associated_with'
    
    # =====================================================================
    # PHASE 3: Claim Consolidation
    # =====================================================================
    
    def _consolidate_claims(self, findings: List[ResearchFinding], report: ResearchReport):
        """Extract, deduplicate, and consolidate claims"""
        # Extract all claims with context
        all_claims = []
        for finding in findings:
            for claim in finding.extracted_claims:
                all_claims.append({
                    'text': claim.claim_text,
                    'type': claim.claim_type,
                    'confidence': claim.confidence * finding.confidence_score,
                    'source': finding.source_reference,
                    'source_tier': self._determine_source_tier(finding.source_type),
                    'finding_id': finding.finding_id,
                    'entities': claim.entities_involved or finding.entities_mentioned
                })
        
        # Deduplicate similar claims (simplified)
        consolidated = self._deduplicate_claims(all_claims)
        
        # Create synthesized claims
        for claim_group in consolidated:
            syn_claim = self._create_synthesized_claim(claim_group)
            
            if syn_claim.confidence == ConfidenceLevel.DISPUTED:
                report.disputed_claims.append(syn_claim)
            else:
                report.verified_claims.append(syn_claim)
        
        # Sort by confidence
        report.verified_claims.sort(
            key=lambda c: c.confidence_score, 
            reverse=True
        )
    
    def _deduplicate_claims(self, claims: List[Dict]) -> List[List[Dict]]:
        """Group similar claims together"""
        # Simple text similarity grouping
        groups = []
        used = set()
        
        for i, claim in enumerate(claims):
            if i in used:
                continue
            
            group = [claim]
            used.add(i)
            
            for j, other in enumerate(claims[i+1:], start=i+1):
                if j in used:
                    continue
                
                # Simple similarity: shared words
                words_a = set(claim['text'].lower().split())
                words_b = set(other['text'].lower().split())
                
                if len(words_a & words_b) / max(len(words_a), len(words_b)) > 0.6:
                    group.append(other)
                    used.add(j)
            
            groups.append(group)
        
        return groups
    
    def _create_synthesized_claim(self, claim_group: List[Dict]) -> SynthesizedClaim:
        """Create unified claim from group of similar claims"""
        # Use best version as base
        best = max(claim_group, key=lambda c: c['confidence'])
        
        # Aggregate sources
        supporting = []
        contradicting = []
        primary_count = 0
        secondary_count = 0
        
        for claim in claim_group:
            source_record = {
                'reference': claim['source'],
                'confidence': claim['confidence'],
                'tier': claim['source_tier']
            }
            
            # Check for contradiction (simplified)
            if claim['confidence'] < 0.3 and best['confidence'] > 0.7:
                contradicting.append(source_record)
            else:
                supporting.append(source_record)
                
                if 'tier_1' in claim['source_tier']:
                    primary_count += 1
                elif 'tier_2' in claim['source_tier']:
                    secondary_count += 1
        
        # Calculate confidence
        has_contradiction = len(contradicting) > 0
        confidence_score = self._calculate_claim_confidence(
            best['confidence'],
            primary_count,
            secondary_count,
            len(supporting),
            has_contradiction
        )
        
        confidence_level = self._score_to_level(confidence_score, has_contradiction)
        
        # Generate gaps and caveats
        gaps = []
        caveats = []
        
        if primary_count == 0:
            gaps.append("No primary source verification")
        if len(supporting) < 2:
            gaps.append("Limited corroboration")
        if len(claim_group) == 1:
            caveats.append("Based on single source")
        
        claim_id = f"claim_{hashlib.md5(best['text'].encode()).hexdigest()[:12]}"
        
        return SynthesizedClaim(
            claim_id=claim_id,
            text=best['text'],
            confidence=confidence_level,
            confidence_score=confidence_score,
            supporting_sources=supporting,
            contradicting_sources=contradicting,
            primary_source_count=primary_count,
            secondary_source_count=secondary_count,
            entities_involved=list(set(e for c in claim_group for e in c['entities'])),
            gaps=gaps,
            caveats=caveats
        )
    
    def _calculate_claim_confidence(self,
                                    base_confidence: float,
                                    primary_sources: int,
                                    secondary_sources: int,
                                    total_supporting: int,
                                    has_contradiction: bool) -> float:
        """Calculate numeric confidence score"""
        score = base_confidence
        
        # Boost for multiple sources
        if total_supporting >= 3:
            score += 0.15
        elif total_supporting >= 2:
            score += 0.08
        
        # Boost for primary sources
        score += min(0.2, primary_sources * 0.1)
        
        # Penalty for lack of primary
        if primary_sources == 0:
            score -= 0.15
        
        # Contradiction penalty
        if has_contradiction:
            score *= 0.7
        
        return max(0.0, min(1.0, score))
    
    def _score_to_level(self, score: float, has_contradiction: bool) -> ConfidenceLevel:
        """Convert numeric score to confidence level"""
        if has_contradiction:
            return ConfidenceLevel.DISPUTED
        
        for level, (low, high) in self.CONFIDENCE_THRESHOLDS.items():
            if level == ConfidenceLevel.DISPUTED:
                continue
            if low <= score <= high:
                return level
        
        return ConfidenceLevel.UNVERIFIED
    
    # =====================================================================
    # PHASE 4: Contradiction Documentation
    # =====================================================================
    
    def _document_contradictions(self, 
                                  findings: List[ResearchFinding], 
                                  report: ResearchReport):
        """Identify and document significant contradictions"""
        # Find claims with both high and low confidence versions
        claim_confidences = defaultdict(list)
        
        for finding in findings:
            for claim in finding.extracted_claims:
                # Normalize claim text for grouping
                key = self._normalize_claim_text(claim.claim_text)
                claim_confidences[key].append({
                    'text': claim.claim_text,
                    'confidence': claim.confidence,
                    'source': finding.source_reference
                })
        
        # Find contradictions
        for key, versions in claim_confidences.items():
            if len(versions) < 2:
                continue
            
            confidences = [v['confidence'] for v in versions]
            max_conf = max(confidences)
            min_conf = min(confidences)
            
            # Significant divergence indicates contradiction
            if max_conf > 0.7 and min_conf < 0.4:
                high_version = max(versions, key=lambda v: v['confidence'])
                low_version = min(versions, key=lambda v: v['confidence'])
                
                contradiction = ContradictionRecord(
                    contradiction_id=f"contr_{hashlib.md5(key.encode()).hexdigest()[:8]}",
                    description=f"Conflicting accounts: {key[:100]}...",
                    severity='high' if max_conf - min_conf > 0.5 else 'medium',
                    position_a={
                        'claims': [high_version['text']],
                        'sources': [high_version['source']],
                        'summary': 'High confidence version'
                    },
                    position_b={
                        'claims': [low_version['text']],
                        'sources': [low_version['source']],
                        'summary': 'Low confidence/Contradicting version'
                    },
                    resolution_status='unresolved',
                    recommended_action='Verify against primary sources'
                )
                
                report.contradictions.append(contradiction)
    
    def _normalize_claim_text(self, text: str) -> str:
        """Normalize claim for comparison"""
        # Remove punctuation, lowercase, sort words
        words = re.sub(r'[^\w\s]', '', text.lower()).split()
        return ' '.join(sorted(words))
    
    # =====================================================================
    # PHASE 5: Timeline Construction
    # =====================================================================
    
    def _build_timeline(self, findings: List[ResearchFinding], report: ResearchReport):
        """Build chronological timeline from dated findings"""
        dated_findings = [f for f in findings if f.source_date]
        
        # Sort by date
        dated_findings.sort(key=lambda f: f.source_date)
        
        # Create events
        for i, finding in enumerate(dated_findings):
            # Extract event description from content
            event_desc = self._extract_event_description(finding)
            
            # Determine date precision
            precision = self._determine_date_precision(finding.source_date)
            
            event = TimelineEvent(
                event_id=f"evt_{finding.finding_id}",
                description=event_desc,
                date=finding.source_date,
                date_precision=precision,
                confidence=ConfidenceLevel.PROBABLE if finding.confidence_score > 0.6 
                          else ConfidenceLevel.POSSIBLE,
                supporting_findings=[finding.finding_id],
                entities_involved=finding.entities_mentioned
            )
            
            # Link to adjacent events
            if i > 0:
                event.preceding_events.append(f"evt_{dated_findings[i-1].finding_id}")
            if i < len(dated_findings) - 1:
                event.following_events.append(f"evt_{dated_findings[i+1].finding_id}")
            
            report.timeline.append(event)
    
    def _extract_event_description(self, finding: ResearchFinding) -> str:
        """Extract what happened from finding content"""
        # Use title if available, else first sentence
        if finding.source_title:
            return finding.source_title
        
        sentences = finding.raw_content.split('.')
        return sentences[0][:150] if sentences else "Event recorded"
    
    def _determine_date_precision(self, date: datetime) -> str:
        """Determine how precise the date is"""
        if date.day != 1 or date.month != 1:
            return 'exact'
        elif date.month != 1:
            return 'month'
        else:
            return 'year'
    
    # =====================================================================
    # PHASE 6: Confidence Grading
    # =====================================================================
    
    def _grade_confidence(self, report: ResearchReport):
        """Calculate overall mission confidence"""
        if not report.verified_claims:
            report.overall_confidence = ConfidenceLevel.UNVERIFIED
            return
        
        # Distribution of claims by confidence
        distribution = defaultdict(int)
        for claim in report.verified_claims:
            distribution[claim.confidence.value] += 1
        
        for claim in report.disputed_claims:
            distribution['disputed'] += 1
        
        report.confidence_distribution = dict(distribution)
        
        # Overall confidence is mode of distribution, capped by disputed ratio
        total_claims = len(report.verified_claims) + len(report.disputed_claims)
        disputed_ratio = len(report.disputed_claims) / total_claims if total_claims > 0 else 0
        
        # Find most common confidence level
        sorted_dist = sorted(distribution.items(), key=lambda x: x[1], reverse=True)
        mode_confidence = sorted_dist[0][0] if sorted_dist else 'unverified'
        
        # Cap if too many disputes
        if disputed_ratio > 0.3:
            report.overall_confidence = ConfidenceLevel.DISPUTED
        else:
            report.overall_confidence = ConfidenceLevel(mode_confidence)
    
    # =====================================================================
    # PHASE 7: Gap Analysis
    # =====================================================================
    
    def _analyze_gaps(self, 
                      findings: List[ResearchFinding], 
                      report: ResearchReport,
                      mission: SwarmMission):
        """Identify research gaps and recommend next steps"""
        gaps = []
        next_steps = []
        verification_needs = []
        followup = []
        
        # Source tier gaps
        primary_sources = report.sources_by_tier.get('tier_1_primary', [])
        if len(primary_sources) < 2:
            gaps.append("Insufficient primary source documentation")
            next_steps.append("Search for government filings, court records, or official statements")
            verification_needs.append("Verify key claims against primary sources")
        
        # Temporal gaps
        if report.timeline:
            dates = [e.date for e in report.timeline if e.date]
            if len(dates) >= 2:
                date_range = (max(dates) - min(dates)).days
                coverage = len(dates) / max(date_range / 30, 1)  # Events per month
                
                if coverage < 0.5:
                    gaps.append(f"Sparse temporal coverage ({coverage:.1f} events/month)")
                    followup.append("Investigate timeline gaps for missing developments")
        
        # Entity gaps
        if len(report.entity_profiles) < 3:
            gaps.append("Limited entity identification")
            next_steps.append("Expand entity extraction to identify key players")
        
        # Claim confidence gaps
        low_confidence_claims = [c for c in report.verified_claims 
                                if c.confidence in [ConfidenceLevel.POSSIBLE, 
                                                   ConfidenceLevel.UNVERIFIED]]
        if len(low_confidence_claims) > len(report.verified_claims) * 0.5:
            gaps.append("High proportion of low-confidence claims")
            verification_needs.append("Prioritize verification of unverified claims")
        
        # Contradiction resolution
        unresolved_contradictions = [c for c in report.contradictions 
                                    if c.resolution_status == 'unresolved']
        if unresolved_contradictions:
            gaps.append(f"{len(unresolved_contradictions)} unresolved contradictions")
            next_steps.append("Resolve contradictions through additional verification")
        
        report.open_questions = list(gaps)
        report.next_steps = list(next_steps)
        report.recommended_verification = list(verification_needs)
        report.suggested_followup = list(followup)
    
    # =====================================================================
    # PHASE 8: Executive Summary
    # =====================================================================
    
    def _generate_executive_summary(self, report: ResearchReport, mission: SwarmMission):
        """Generate concise executive summary"""
        parts = []
        
        # Opening
        parts.append(f"Research on '{mission.topic}' synthesized {report.synthesis_stats['findings_processed']} "
                    f"findings from {report.synthesis_stats['unique_sources']} sources.")
        
        # Key findings overview
        verified_count = len([c for c in report.verified_claims 
                             if c.confidence in [ConfidenceLevel.VERIFIED, 
                                                ConfidenceLevel.HIGHLY_PROBABLE]])
        parts.append(f"Identified {verified_count} verified claims and "
                    f"{len(report.entity_profiles)} key entities.")
        
        # Confidence assessment
        if report.overall_confidence == ConfidenceLevel.VERIFIED:
            parts.append("Findings are well-supported by multiple primary sources.")
        elif report.overall_confidence == ConfidenceLevel.DISPUTED:
            parts.append("Significant contradictions exist requiring resolution.")
        else:
            parts.append(f"Overall confidence: {report.overall_confidence.value}. "
                        f"Additional verification recommended.")
        
        # Critical entities
        if report.entity_profiles:
            top_entities = sorted(report.entity_profiles.values(),
                                key=lambda e: e.mention_count,
                                reverse=True)[:3]
            entity_names = [e.name for e in top_entities]
            parts.append(f"Key entities: {', '.join(entity_names)}.")
        
        report.executive_summary = " ".join(parts)
        
        # Key takeaways
        takeaways = []
        
        # Top verified claims as takeaways
        for claim in report.verified_claims[:3]:
            if claim.confidence in [ConfidenceLevel.VERIFIED, ConfidenceLevel.HIGHLY_PROBABLE]:
                takeaways.append(claim.text[:150])
        
        # Add contradiction warning if present
        if report.contradictions:
            takeaways.append(f"⚠️  {len(report.contradictions)} contradictions require attention")
        
        # Add gap warning
        if report.open_questions:
            takeaways.append(f"📋 {len(report.open_questions)} research gaps identified")
        
        report.key_takeaways = takeaways


# ============================================================================
# INTEGRATION INTERFACE
# ============================================================================

class SynthesisPipeline:
    """
    High-level interface for synthesis operations.
    Integrates with SwarmResearchOrchestrator.
    """
    
    def __init__(self):
        self.engine = SynthesisEngine()
        self.synthesis_history: List[ResearchReport] = []
    
    async def synthesize_mission(self,
                                  mission: SwarmMission,
                                  orbs: List[OrbInstance]) -> ResearchReport:
        """
        Complete synthesis pipeline for a mission.
        """
        # Collect all findings from all orbs
        all_findings = []
        for orb in orbs:
            all_findings.extend(orb.findings)
        
        # Deduplicate findings by source
        seen_sources = set()
        unique_findings = []
        for finding in all_findings:
            key = (finding.source_reference, finding.source_type)
            if key not in seen_sources:
                seen_sources.add(key)
                unique_findings.append(finding)
        
        logger.info(f"Synthesizing {len(unique_findings)} unique findings "
                   f"(deduplicated from {len(all_findings)})")
        
        # Run synthesis
        report = self.engine.synthesize(unique_findings, mission, orbs)
        
        # Store
        self.synthesis_history.append(report)
        
        return report
    
    def get_report(self, report_id: str) -> Optional[ResearchReport]:
        """Retrieve report by ID"""
        for report in self.synthesis_history:
            if report.report_id == report_id:
                return report
        return None
    
    def compare_reports(self, report_a_id: str, report_b_id: str) -> Dict:
        """Compare two synthesis reports for divergence"""
        report_a = self.get_report(report_a_id)
        report_b = self.get_report(report_b_id)
        
        if not report_a or not report_b:
            return {'error': 'Report not found'}
        
        # Compare entity overlap
        entities_a = set(report_a.entity_profiles.keys())
        entities_b = set(report_b.entity_profiles.keys())
        
        # Compare claim overlap
        claims_a = {c.claim_id for c in report_a.verified_claims}
        claims_b = {c.claim_id for c in report_b.verified_claims}
        
        return {
            'entity_overlap': {
                'common': len(entities_a & entities_b),
                'only_in_a': len(entities_a - entities_b),
                'only_in_b': len(entities_b - entities_a)
            },
            'claim_overlap': {
                'common': len(claims_a & claims_b),
                'only_in_a': len(claims_a - claims_b),
                'only_in_b': len(claims_b - claims_a)
            },
            'confidence_divergence': abs(report_a.overall_confidence.value != 
                                        report_b.overall_confidence.value)
        }


# ============================================================================
# USAGE EXAMPLE
# ============================================================================

def example_usage():
    """Demonstrate synthesis capabilities"""
    
    from epistemic_swarm_governor_skg import OrbInstance, OrbClass, OrbState
    
    # Create mock mission
    class MockMission:
        def __init__(self):
            self.mission_id = "mission_001"
            self.topic = "Halo Pets Acquisition by Better Choice Company"
            self.mission_type = MissionType.DEEP_INVESTIGATION
    
    mission = MockMission()
    
    # Create mock orbs with findings
    orbs = []
    
    # Scout orb findings
    scout = OrbInstance(
        orb_id="orb_scout_1",
        orb_class=OrbClass.SCOUT,
        lane="discovery",
        mission_id="mission_001"
    )
    scout.findings = [
        ResearchFinding(
            finding_id="find_001",
            orb_id="orb_scout_1",
            orb_class=OrbClass.SCOUT,
            source_type="web",
            source_reference="https://example.com/news1",
            source_title="Better Choice Acquires Halo Pets",
            source_date=datetime(2021, 6, 15),
            raw_content="Better Choice Company announced the acquisition of Halo Pets "
                       "for $50 million. The deal was finalized in June 2021.",
            extracted_claims=[
                ExtractedClaim(
                    claim_text="Better Choice acquired Halo Pets for $50 million",
                    claim_type="factual",
                    confidence=0.8
                ),
                ExtractedClaim(
                    claim_text="Deal finalized in June 2021",
                    claim_type="factual",
                    confidence=0.9
                )
            ],
            entities_mentioned=["Better Choice Company", "Halo Pets", "$50 million", "June 2021"],
            confidence_score=0.75
        ),
        ResearchFinding(
            finding_id="find_002",
            orb_id="orb_scout_1",
            orb_class=OrbClass.SCOUT,
            source_type="web",
            source_reference="https://example.com/news2",
            source_title="Industry Reacts to Halo Acquisition",
            source_date=datetime(2021, 6, 20),
            raw_content="Industry analysts praised the acquisition. Halo Pets founder "
                       "Lori Taylor will remain as CEO.",
            extracted_claims=[
                ExtractedClaim(
                    claim_text="Lori Taylor remains CEO of Halo Pets",
                    claim_type="factual",
                    confidence=0.7
                )
            ],
            entities_mentioned=["Lori Taylor", "Halo Pets", "CEO"],
            confidence_score=0.7
        )
    ]
    orbs.append(scout)
    
    # Archivist orb findings (primary source)
    archivist = OrbInstance(
        orb_id="orb_archivist_1",
        orb_class=OrbClass.ARCHIVIST,
        lane="filings",
        mission_id="mission_001"
    )
    archivist.findings = [
        ResearchFinding(
            finding_id="find_003",
            orb_id="orb_archivist_1",
            orb_class=OrbClass.ARCHIVIST,
            source_type="sec_filing",
            source_reference="SEC-8K-2021-0615",
            source_title="Form 8-K: Acquisition of Halo Pets",
            source_date=datetime(2021, 6, 15),
            raw_content="Item 1.01 Entry into Material Definitive Agreement. "
                       "On June 15, 2021, Better Choice Company entered into an "
                       "agreement to acquire Halo Pets, Inc. for consideration of "
                       "$50 million in cash and stock.",
            extracted_claims=[
                ExtractedClaim(
                    claim_text="Acquisition price $50 million in cash and stock",
                    claim_type="factual",
                    confidence=0.95
                ),
                ExtractedClaim(
                    claim_text="Agreement dated June 15, 2021",
                    claim_type="factual",
                    confidence=0.98
                )
            ],
            entities_mentioned=["Better Choice Company", "Halo Pets, Inc.", "$50 million"],
            confidence_score=0.95,
            source_quality_tier=1
        )
    ]
    orbs.append(archivist)
    
    # Verifier orb findings (contradiction)
    verifier = OrbInstance(
        orb_id="orb_verifier_1",
        orb_class=OrbClass.VERIFIER,
        lane="verification",
        mission_id="mission_001"
    )
    verifier.findings = [
        ResearchFinding(
            finding_id="find_004",
            orb_id="orb_verifier_1",
            orb_class=OrbClass.VERIFIER,
            source_type="web",
            source_reference="https://example.com/rumor",
            source_title="Questions About Halo Deal",
            source_date=datetime(2021, 7, 1),
            raw_content="Some sources suggest the deal was actually $45 million, "
                       "not $50 million as reported.",
            extracted_claims=[
                ExtractedClaim(
                    claim_text="Deal value was $45 million, not $50 million",
                    claim_type="disputed",
                    confidence=0.3
                )
            ],
            entities_mentioned=["Halo", "$45 million", "$50 million"],
            confidence_score=0.3
        )
    ]
    orbs.append(verifier)
    
    # Run synthesis
    pipeline = SynthesisPipeline()
    
    import asyncio
    report = asyncio.run(pipeline.synthesize_mission(mission, orbs))
    
    # Output
    print("=" * 60)
    print("SYNTHESIS REPORT")
    print("=" * 60)
    print(f"\nReport ID: {report.report_id}")
    print(f"Topic: {report.topic}")
    print(f"Overall Confidence: {report.overall_confidence.value.upper()}")
    print(f"\nExecutive Summary:\n{report.executive_summary}")
    
    print(f"\n--- Key Takeaways ---")
    for i, takeaway in enumerate(report.key_takeaways, 1):
        print(f"{i}. {takeaway}")
    
    print(f"\n--- Verified Claims ({len(report.verified_claims)}) ---")
    for claim in report.verified_claims[:5]:
        print(f"\n[{claim.confidence.value.upper()}] {claim.text[:80]}...")
        print(f"   Confidence: {claim.confidence_score:.2f} | "
              f"Primary: {claim.primary_source_count} | "
              f"Secondary: {claim.secondary_source_count}")
        if claim.caveats:
            print(f"   Caveats: {', '.join(claim.caveats)}")
    
    print(f"\n--- Disputed Claims ({len(report.disputed_claims)}) ---")
    for claim in report.disputed_claims:
        print(f"\n⚠️  {claim.text[:80]}...")
        print(f"   Supporting: {len(claim.supporting_sources)} | "
              f"Contradicting: {len(claim.contradicting_sources)}")
    
    print(f"\n--- Entities ({len(report.entity_profiles)}) ---")
    for entity in list(report.entity_profiles.values())[:5]:
        print(f"\n• {entity.name} ({entity.entity_type})")
        print(f"  Mentioned {entity.mention_count} times, "
              f"{entity.source_diversity} sources")
        if entity.relationships:
            for rel in entity.relationships[:3]:
                print(f"  → {rel['type']} {rel['target_entity']}")
    
    print(f"\n--- Contradictions ({len(report.contradictions)}) ---")
    for contr in report.contradictions:
        print(f"\n⚠️  [{contr.severity.upper()}] {contr.description}")
        print(f"   Status: {contr.resolution_status}")
        print(f"   Action: {contr.recommended_action}")
    
    print(f"\n--- Gaps & Recommendations ---")
    for gap in report.open_questions[:3]:
        print(f"❓ {gap}")
    for step in report.next_steps[:3]:
        print(f"➡️  {step}")
    
    print(f"\n--- Markdown Output Preview ---")
    print(report.to_markdown()[:500] + "...\n")
    
    print(f"\nStats: {report.synthesis_stats}")


if __name__ == "__main__":
    example_usage()
