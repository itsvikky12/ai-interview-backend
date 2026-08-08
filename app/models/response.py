import uuid
from datetime import datetime, timezone

from typing import Optional, Any
from sqlalchemy import String, DateTime, Float, ForeignKey, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Response(Base):
    __tablename__ = "responses"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    interview_id: Mapped[str] = mapped_column(String(36), ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True)
    question_id: Mapped[str] = mapped_column(String(36), ForeignKey("questions.id", ondelete="CASCADE"), nullable=False, unique=True)
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    audio_url: Mapped[Optional[str]] = mapped_column(String(500))

    # Scoring
    score: Mapped[Optional[float]] = mapped_column(Float)
    feedback: Mapped[Optional[str]] = mapped_column(Text)
    strengths: Mapped[Optional[Any]] = mapped_column(JSON)
    weaknesses: Mapped[Optional[Any]] = mapped_column(JSON)

    # Speech metrics for this response
    wpm: Mapped[Optional[float]] = mapped_column(Float)
    filler_word_count: Mapped[Optional[int]] = mapped_column()
    pause_count: Mapped[Optional[int]] = mapped_column()
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    interview: Mapped["Interview"] = relationship(back_populates="responses")
    question: Mapped["Question"] = relationship(back_populates="response")
