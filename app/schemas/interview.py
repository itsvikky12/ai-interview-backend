from pydantic import BaseModel, Field
from typing import Optional
from uuid import UUID
from datetime import datetime


class InterviewCreate(BaseModel):
    target_role: str = Field(min_length=2, max_length=255)
    resume_id: Optional[UUID] = None
    language: str = Field(default="english", pattern="^(english|hindi|hinglish)$")


class InterviewResponse(BaseModel):
    id: UUID
    user_id: UUID
    resume_id: Optional[UUID] = None
    target_role: str
    status: str
    current_phase: str
    difficulty_level: float
    language: str
    technical_score: Optional[float] = None
    communication_score: Optional[float] = None
    confidence_score: Optional[float] = None
    overall_score: Optional[float] = None
    total_questions: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class InterviewListItem(BaseModel):
    id: UUID
    target_role: str
    status: str
    overall_score: Optional[float] = None
    total_questions: int
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class QuestionOut(BaseModel):
    id: UUID
    question_text: str
    question_type: str
    difficulty: float
    topic: Optional[str] = None
    order_index: int

    model_config = {"from_attributes": True}


class AnswerSubmit(BaseModel):
    question_id: UUID
    answer_text: str
    audio_url: Optional[str] = None
    duration_seconds: Optional[float] = None


class AnswerFeedback(BaseModel):
    question_id: UUID
    score: float
    feedback: str
    strengths: list[str] = []
    weaknesses: list[str] = []


class WSMessage(BaseModel):
    type: str  # "answer", "next_question", "phase_change", "end", "proctor_event", "speech_chunk"
    data: dict = {}


class InterviewStateOut(BaseModel):
    interview_id: UUID
    phase: str
    question_index: int
    difficulty: float
    time_remaining_seconds: int
    current_question: Optional[QuestionOut] = None
