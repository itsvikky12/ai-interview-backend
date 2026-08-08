from pydantic import BaseModel
from typing import Optional
from uuid import UUID
from datetime import datetime


class ReportResponse(BaseModel):
    id: UUID
    interview_id: UUID
    technical_score: float
    communication_score: float
    confidence_score: float
    overall_score: float
    strengths: Optional[list[str]] = None
    weaknesses: Optional[list[str]] = None
    skill_gaps: Optional[dict] = None
    improvement_roadmap: Optional[list[dict]] = None
    question_scores: Optional[list[dict]] = None
    summary: Optional[str] = None
    pdf_url: Optional[str] = None
    created_at: datetime

    model_config = {"from_attributes": True}


class AdminAnalytics(BaseModel):
    total_users: int
    total_interviews: int
    completed_interviews: int
    average_score: Optional[float] = None
    score_distribution: dict = {}
    interviews_per_day: list[dict] = []
    top_roles: list[dict] = []
    flagged_sessions: int = 0
