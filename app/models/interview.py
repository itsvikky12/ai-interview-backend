import uuid
import enum
from datetime import datetime, timezone
from typing import Optional, Any
from sqlalchemy import String, DateTime, Float, Integer, ForeignKey, Enum as SAEnum, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class InterviewStatus(str, enum.Enum):
    SCHEDULED = "scheduled"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    FLAGGED = "flagged"


class InterviewPhase(str, enum.Enum):
    INTRODUCTION = "introduction"
    TECHNICAL = "technical"
    SYSTEM_DESIGN = "system_design"
    HR = "hr"
    CODING_ASSESSMENT = "coding_assessment"
    COMPLETED = "completed"


class Interview(Base):
    __tablename__ = "interviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    resume_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("resumes.id", ondelete="SET NULL"))
    target_role: Mapped[str] = mapped_column(String(255), nullable=False)
    difficulty_level: Mapped[float] = mapped_column(Float, default=5.0)  # 1-10 scale
    status: Mapped[InterviewStatus] = mapped_column(SAEnum(InterviewStatus), default=InterviewStatus.SCHEDULED)
    current_phase: Mapped[InterviewPhase] = mapped_column(SAEnum(InterviewPhase), default=InterviewPhase.INTRODUCTION)
    language: Mapped[str] = mapped_column(String(20), default="english")

    # Scores
    technical_score: Mapped[Optional[float]] = mapped_column(Float)
    communication_score: Mapped[Optional[float]] = mapped_column(Float)
    confidence_score: Mapped[Optional[float]] = mapped_column(Float)
    coding_score: Mapped[Optional[float]] = mapped_column(Float)
    overall_score: Mapped[Optional[float]] = mapped_column(Float)

    # Metadata
    total_questions: Mapped[int] = mapped_column(Integer, default=0)
    recording_url: Mapped[Optional[str]] = mapped_column(String(500))
    feedback_summary: Mapped[Optional[str]] = mapped_column(Text)
    anti_cheat_flags: Mapped[Optional[Any]] = mapped_column(JSON)
    speech_metrics: Mapped[Optional[Any]] = mapped_column(JSON)
    emotion_metrics: Mapped[Optional[Any]] = mapped_column(JSON)

    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="interviews")
    resume: Mapped["Resume"] = relationship()
    questions: Mapped[list["Question"]] = relationship(back_populates="interview", cascade="all, delete-orphan")
    responses: Mapped[list["Response"]] = relationship(back_populates="interview", cascade="all, delete-orphan")
    proctor_events: Mapped[list["ProctorEvent"]] = relationship(back_populates="interview", cascade="all, delete-orphan")
    report: Mapped["Report"] = relationship(back_populates="interview", uselist=False, cascade="all, delete-orphan")
