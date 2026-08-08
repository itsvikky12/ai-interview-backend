import uuid
import enum
from datetime import datetime, timezone, timedelta
from typing import Optional, Any
from sqlalchemy import String, DateTime, Float, Integer, ForeignKey, Enum as SAEnum, Text, JSON, Boolean
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class RecordingStatus(str, enum.Enum):
    RECORDING = "recording"
    UPLOADING = "uploading"
    PROCESSING = "processing"
    READY = "ready"
    FAILED = "failed"
    EXPIRED = "expired"
    DELETED = "deleted"


class InterviewRecording(Base):
    __tablename__ = "interview_recordings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    interview_id: Mapped[str] = mapped_column(String(36), ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True)
    student_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    recording_url: Mapped[Optional[str]] = mapped_column(String(500))
    thumbnail_url: Mapped[Optional[str]] = mapped_column(String(500))
    transcript_url: Mapped[Optional[str]] = mapped_column(String(500))
    pdf_report_url: Mapped[Optional[str]] = mapped_column(String(500))

    duration: Mapped[float] = mapped_column(Float, default=0.0)
    resolution: Mapped[str] = mapped_column(String(20), default="720p")
    format: Mapped[str] = mapped_column(String(10), default="mp4")
    file_size: Mapped[int] = mapped_column(Integer, default=0)

    upload_status: Mapped[RecordingStatus] = mapped_column(SAEnum(RecordingStatus), default=RecordingStatus.RECORDING, nullable=False)
    storage_provider: Mapped[str] = mapped_column(String(50), default="s3")

    download_count: Mapped[int] = mapped_column(Integer, default=0)
    view_count: Mapped[int] = mapped_column(Integer, default=0)
    last_viewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    ai_markers: Mapped[Optional[Any]] = mapped_column(JSON)
    is_extended: Mapped[bool] = mapped_column(Boolean, default=False)
    expiry_warning_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc) + timedelta(days=7),
        nullable=False,
        index=True
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    interview: Mapped["Interview"] = relationship()
    student: Mapped["User"] = relationship()
    audit_logs: Mapped[list["RecordingAuditLog"]] = relationship(back_populates="recording", cascade="all, delete-orphan")


class RecordingAuditLog(Base):
    __tablename__ = "recording_audit_logs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    recording_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("interview_recordings.id", ondelete="SET NULL"))
    actor_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("users.id", ondelete="SET NULL"))
    actor_role: Mapped[str] = mapped_column(String(50), default="student")
    action: Mapped[str] = mapped_column(String(100), nullable=False)
    details: Mapped[Optional[Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    recording: Mapped["InterviewRecording"] = relationship(back_populates="audit_logs")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    type: Mapped[str] = mapped_column(String(50), default="info") # info, warning, success, danger
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    link: Mapped[Optional[str]] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped["User"] = relationship()
