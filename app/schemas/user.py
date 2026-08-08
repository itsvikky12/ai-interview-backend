from pydantic import BaseModel, Field
from typing import Optional, Union, Any
from uuid import UUID
from datetime import datetime


class UserProfile(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    bio: Optional[str] = None
    target_role: Optional[str] = None
    experience_years: Optional[int] = None
    college: Optional[str] = None
    department: Optional[str] = None
    course: Optional[str] = None
    year: Optional[int] = None
    skills: Optional[Union[list, dict, Any]] = None
    is_active: bool
    must_change_password: bool = False
    created_at: datetime

    model_config = {"from_attributes": True}


class UserUpdate(BaseModel):
    full_name: Optional[str] = Field(None, min_length=2, max_length=255)
    phone: Optional[str] = Field(None, max_length=20)
    bio: Optional[str] = None
    target_role: Optional[str] = Field(None, max_length=255)
    experience_years: Optional[int] = Field(None, ge=0, le=50)
    college: Optional[str] = None
    department: Optional[str] = None
    course: Optional[str] = None
    year: Optional[int] = None
    skills: Optional[list] = None


class UserListItem(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    phone: Optional[str] = None
    college: Optional[str] = None
    department: Optional[str] = None
    course: Optional[str] = None
    year: Optional[int] = None
    is_active: bool
    created_at: datetime
    interview_count: int = 0
    avg_score: Optional[float] = None

    model_config = {"from_attributes": True}


class StudentCreateRequest(BaseModel):
    email: str
    password: str = Field("Student@123", min_length=6)
    full_name: str
    phone: Optional[str] = None
    college: Optional[str] = None
    department: Optional[str] = None
    course: Optional[str] = None
    year: Optional[int] = None
    skills: Optional[list[str]] = None


class StudentUpdateRequest(BaseModel):
    full_name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    college: Optional[str] = None
    department: Optional[str] = None
    course: Optional[str] = None
    year: Optional[int] = None
    skills: Optional[list[str]] = None
    is_active: Optional[bool] = None


class BulkEmailRequest(BaseModel):
    student_ids: list[str]
    subject: str
    body: str


class BulkAssignInterviewRequest(BaseModel):
    student_ids: list[str]
    target_role: str
    difficulty_level: float = 5.0
    language: str = "english"

