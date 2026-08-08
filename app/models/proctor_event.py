import uuid
import enum
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy import String, DateTime, Float, ForeignKey, Enum as SAEnum, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class EventType(str, enum.Enum):
    TAB_SWITCH = "tab_switch"
    MULTIPLE_FACES = "multiple_faces"
    NO_FACE = "no_face"
    GAZE_DEVIATION = "gaze_deviation"
    COPY_PASTE = "copy_paste"
    WINDOW_BLUR = "window_blur"
    SUSPICIOUS_AUDIO = "suspicious_audio"


class SeverityLevel(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class ProctorEvent(Base):
    __tablename__ = "proctor_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    interview_id: Mapped[str] = mapped_column(String(36), ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True)
    event_type: Mapped[EventType] = mapped_column(SAEnum(EventType), nullable=False)
    severity: Mapped[SeverityLevel] = mapped_column(SAEnum(SeverityLevel), default=SeverityLevel.LOW)
    details: Mapped[Optional[str]] = mapped_column(Text)
    metadata_json: Mapped[Optional[Any]] = mapped_column(JSON)
    confidence: Mapped[Optional[float]] = mapped_column(Float)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    interview: Mapped["Interview"] = relationship(back_populates="proctor_events")
