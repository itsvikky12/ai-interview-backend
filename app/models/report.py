import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import String, DateTime, Float, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    interview_id: Mapped[str] = mapped_column(String(36), ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, unique=True)

    # Aggregated scores
    technical_score: Mapped[float] = mapped_column(Float, default=0.0)
    communication_score: Mapped[float] = mapped_column(Float, default=0.0)
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    coding_score: Mapped[float] = mapped_column(Float, default=0.0)
    overall_score: Mapped[float] = mapped_column(Float, default=0.0)

    # Detailed breakdown — strengths/weaknesses are list[str], others are dict/list
    strengths: Mapped[Optional[Any]] = mapped_column(JSON)
    weaknesses: Mapped[Optional[Any]] = mapped_column(JSON)
    skill_gaps: Mapped[Optional[Any]] = mapped_column(JSON)
    improvement_roadmap: Mapped[Optional[Any]] = mapped_column(JSON)
    question_scores: Mapped[Optional[Any]] = mapped_column(JSON)
    coding_breakdown: Mapped[Optional[Any]] = mapped_column(JSON)

    summary: Mapped[Optional[str]] = mapped_column(Text)
    pdf_url: Mapped[Optional[str]] = mapped_column(String(500))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    interview: Mapped["Interview"] = relationship(back_populates="report")
