from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional, List, Dict, Any


class RecordingCreate(BaseModel):
    interview_id: str
    resolution: str = Field(default="720p", description="720p or 1080p")
    format: str = Field(default="mp4", description="mp4 or webm")


class RecordingChunkUpload(BaseModel):
    chunk_index: int
    total_chunks: Optional[int] = None
    chunk_data_base64: str


class RecordingCompleteUpload(BaseModel):
    duration: float
    resolution: str = "720p"


class RecordingExtendExpiry(BaseModel):
    additional_days: int = Field(default=7, ge=1, le=30)


class RecordingResponse(BaseModel):
    id: str
    interview_id: str
    student_id: str
    recording_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    transcript_url: Optional[str] = None
    pdf_report_url: Optional[str] = None
    duration: float
    resolution: str
    format: str
    file_size: int
    upload_status: str
    storage_provider: str
    download_count: int
    view_count: int
    last_viewed_at: Optional[datetime] = None
    ai_markers: Optional[Dict[str, Any]] = None
    is_extended: bool
    created_at: datetime
    expires_at: datetime
    deleted_at: Optional[datetime] = None
    
    # Extra joined details for UI rendering
    interview_target_role: Optional[str] = None
    student_name: Optional[str] = None
    company_name: Optional[str] = None
    overall_score: Optional[float] = None
    remaining_days: Optional[float] = None

    model_config = {"from_attributes": True}


class AdminRecordingStats(BaseModel):
    total_recordings: int
    total_storage_bytes: int
    active_recordings: int
    expiring_today: int
    deleted_today: int
    daily_uploads_count: int


class NotificationResponse(BaseModel):
    id: str
    user_id: str
    title: str
    message: str
    type: str
    is_read: bool
    link: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
