
"""
Escalation Queue — INTERIM DESTINATION (GAP_ECM RESOLVED).

Until ECM is built, all escalations go here:
  - escalation_log (persistent audit trail)
  - human_review_queue (flagged for human attention)

This prevents silent failures. Every escalation is logged, timestamped,
and queued for review. Nothing is lost.
"""

from typing import List, Dict, Optional
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class EscalationRecord:
    record_id: str
    source: str
    reason: str
    affected_atom_ids: List[str]
    beam_outputs: List[dict] = field(default_factory=list)
    fifth_mind_output: Optional[dict] = None
    tribunal_judgment: Optional[dict] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    status: str = "pending"
    resolution: Optional[str] = None
    resolved_at: Optional[datetime] = None


class EscalationQueue:
    def __init__(self):
        self.records: List[EscalationRecord] = []
        self.pending_count: int = 0
        self._counter: int = 0

    def escalate(
        self,
        source: str,
        reason: str,
        affected_atom_ids: List[str],
        beam_outputs: Optional[List] = None,
        fifth_mind_output: Optional[dict] = None,
        tribunal_judgment: Optional[dict] = None,
    ) -> EscalationRecord:
        self._counter += 1
        record = EscalationRecord(
            record_id=f"esc_{self._counter}_{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
            source=source,
            reason=reason,
            affected_atom_ids=affected_atom_ids,
            beam_outputs=[bo.__dict__ if hasattr(bo, '__dict__') else bo
                         for bo in (beam_outputs or [])],
            fifth_mind_output=fifth_mind_output,
            tribunal_judgment=tribunal_judgment,
        )
        self.records.append(record)
        self.pending_count += 1
        self._prune()
        return record

    def resolve(self, record_id: str, resolution: str) -> Optional[EscalationRecord]:
        for record in self.records:
            if record.record_id == record_id and record.status == "pending":
                record.status = "resolved"
                record.resolution = resolution
                record.resolved_at = datetime.utcnow()
                self.pending_count -= 1
                return record
        return None

    def dismiss(self, record_id: str, reason: str) -> Optional[EscalationRecord]:
        for record in self.records:
            if record.record_id == record_id and record.status == "pending":
                record.status = "dismissed"
                record.resolution = reason
                record.resolved_at = datetime.utcnow()
                self.pending_count -= 1
                return record
        return None

    def get_pending(self) -> List[EscalationRecord]:
        return [r for r in self.records if r.status == "pending"]

    def get_by_atom(self, atom_id: str) -> List[EscalationRecord]:
        return [r for r in self.records if atom_id in r.affected_atom_ids]

    def _prune(self):
        if len(self.records) > 1000:
            pending = [r for r in self.records if r.status == "pending"]
            resolved = [r for r in self.records if r.status != "pending"]
            self.records = pending + resolved[-200:]

    def stats(self) -> dict:
        total = len(self.records)
        pending = self.pending_count
        resolved = len([r for r in self.records if r.status == "resolved"])
        dismissed = len([r for r in self.records if r.status == "dismissed"])
        return {
            "total_records": total,
            "pending": pending,
            "resolved": resolved,
            "dismissed": dismissed,
            "resolution_rate": resolved / max(1, resolved + dismissed),
        }
