import uuid
import enum
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy import String, DateTime, Float, Integer, ForeignKey, Enum as SAEnum, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class QuestionType(str, enum.Enum):
    INTRODUCTION = "introduction"
    TECHNICAL = "technical"
    SYSTEM_DESIGN = "system_design"
    BEHAVIORAL = "behavioral"
    HR = "hr"
    FOLLOW_UP = "follow_up"


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    interview_id: Mapped[str] = mapped_column(String(36), ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[QuestionType] = mapped_column(SAEnum(QuestionType), nullable=False)
    difficulty: Mapped[float] = mapped_column(Float, default=5.0)
    order_index: Mapped[int] = mapped_column(Integer, nullable=False)
    topic: Mapped[Optional[str]] = mapped_column(String(255))
    expected_keywords: Mapped[Optional[str]] = mapped_column(Text)
    max_score: Mapped[float] = mapped_column(Float, default=10.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    interview: Mapped["Interview"] = relationship(back_populates="questions")
    response: Mapped["Response"] = relationship(back_populates="question", uselist=False)
