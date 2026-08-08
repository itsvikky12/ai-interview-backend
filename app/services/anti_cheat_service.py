from __future__ import annotations
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.models.proctor_event import ProctorEvent, EventType, SeverityLevel
from app.models.interview import Interview, InterviewStatus
from app.utils.logger import get_logger

logger = get_logger(__name__)

SEVERITY_THRESHOLDS = {
    EventType.TAB_SWITCH: {"low": 2, "medium": 5, "high": 10},
    EventType.MULTIPLE_FACES: {"low": 1, "medium": 2, "high": 3},
    EventType.NO_FACE: {"low": 5, "medium": 15, "high": 30},
    EventType.GAZE_DEVIATION: {"low": 10, "medium": 25, "high": 50},
    EventType.COPY_PASTE: {"low": 1, "medium": 3, "high": 5},
    EventType.WINDOW_BLUR: {"low": 3, "medium": 8, "high": 15},
}

FLAG_THRESHOLD = 15


class AntiCheatService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_event(self, interview_id: UUID, event_type: str, details: str | None = None, metadata: dict | None = None, confidence: float | None = None) -> ProctorEvent:
        try:
            evt_type = EventType(event_type)
        except ValueError:
            logger.warning("unknown_proctor_event", event_type=event_type)
            evt_type = EventType.TAB_SWITCH

        # Count existing events of this type
        result = await self.db.execute(
            select(func.count(ProctorEvent.id)).where(
                ProctorEvent.interview_id == interview_id,
                ProctorEvent.event_type == evt_type,
            )
        )
        count = result.scalar() or 0
        severity = self._calculate_severity(evt_type, count + 1)

        event = ProctorEvent(
            interview_id=interview_id,
            event_type=evt_type,
            severity=severity,
            details=details,
            metadata_json=metadata,
            confidence=confidence,
        )
        self.db.add(event)
        await self.db.flush()

        # Check if interview should be flagged
        total_events = await self._get_total_severity_score(interview_id)
        if total_events >= FLAG_THRESHOLD:
            await self._flag_interview(interview_id)

        logger.info("proctor_event_logged", interview_id=str(interview_id), event_type=event_type, severity=severity.value)
        return event

    async def get_events(self, interview_id: UUID) -> list[ProctorEvent]:
        result = await self.db.execute(
            select(ProctorEvent)
            .where(ProctorEvent.interview_id == interview_id)
            .order_by(ProctorEvent.timestamp.asc())
        )
        return list(result.scalars().all())

    async def get_summary(self, interview_id: UUID) -> dict:
        events = await self.get_events(interview_id)
        summary = {}
        for event in events:
            key = event.event_type.value
            if key not in summary:
                summary[key] = {"count": 0, "max_severity": "low"}
            summary[key]["count"] += 1
            if self._severity_rank(event.severity) > self._severity_rank(SeverityLevel(summary[key]["max_severity"])):
                summary[key]["max_severity"] = event.severity.value

        total_score = await self._get_total_severity_score(interview_id)
        return {
            "events": summary,
            "total_events": len(events),
            "risk_score": min(100, int(total_score * (100 / FLAG_THRESHOLD))),
            "flagged": total_score >= FLAG_THRESHOLD,
        }

    def _calculate_severity(self, event_type: EventType, count: int) -> SeverityLevel:
        thresholds = SEVERITY_THRESHOLDS.get(event_type, {"low": 3, "medium": 7, "high": 15})
        if count >= thresholds["high"]:
            return SeverityLevel.CRITICAL
        elif count >= thresholds["medium"]:
            return SeverityLevel.HIGH
        elif count >= thresholds["low"]:
            return SeverityLevel.MEDIUM
        return SeverityLevel.LOW

    async def _get_total_severity_score(self, interview_id: UUID) -> int:
        """Calculate total severity score using a single SQL query with CASE weights."""
        from sqlalchemy import case as sa_case
        result = await self.db.execute(
            select(
                func.sum(
                    sa_case(
                        (ProctorEvent.severity == SeverityLevel.CRITICAL, 5),
                        (ProctorEvent.severity == SeverityLevel.HIGH, 3),
                        (ProctorEvent.severity == SeverityLevel.MEDIUM, 2),
                        else_=1,
                    )
                )
            ).where(ProctorEvent.interview_id == interview_id)
        )
        return result.scalar() or 0

    async def _flag_interview(self, interview_id: UUID) -> None:
        result = await self.db.execute(select(Interview).where(Interview.id == interview_id))
        interview = result.scalar_one_or_none()
        if interview and interview.status == InterviewStatus.IN_PROGRESS:
            interview.status = InterviewStatus.FLAGGED
            summary = await self.get_summary(interview_id)
            interview.anti_cheat_flags = summary
            logger.warning("interview_flagged", interview_id=str(interview_id))

    def _severity_rank(self, severity: SeverityLevel) -> int:
        return {"low": 0, "medium": 1, "high": 2, "critical": 3}.get(severity.value, 0)
