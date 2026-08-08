import uuid
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import String, DateTime, Text, ForeignKey, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class Resume(Base):
    __tablename__ = "resumes"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    file_url: Mapped[str] = mapped_column(String(500), nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    raw_text: Mapped[Optional[str]] = mapped_column(Text)

    # Structured extracted data — stored as JSON arrays
    skills: Mapped[Optional[Any]] = mapped_column(JSON)
    projects: Mapped[Optional[Any]] = mapped_column(JSON)
    experience: Mapped[Optional[Any]] = mapped_column(JSON)
    education: Mapped[Optional[Any]] = mapped_column(JSON)
    certifications: Mapped[Optional[Any]] = mapped_column(JSON)
    research_papers: Mapped[Optional[Any]] = mapped_column(JSON)
    achievements: Mapped[Optional[Any]] = mapped_column(JSON)
    summary: Mapped[Optional[str]] = mapped_column(Text)

    is_primary: Mapped[bool] = mapped_column(default=False)
    parsed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship(back_populates="resumes")
