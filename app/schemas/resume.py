from pydantic import BaseModel
from typing import Optional, Any
from uuid import UUID
from datetime import datetime


class SkillItem(BaseModel):
    name: str
    category: str  # e.g. "programming_language", "framework", "database", "tool", "cloud_platform", "ai_ml", "soft_skill"
    proficiency: Optional[str] = None  # beginner, intermediate, advanced, expert


class ProjectItem(BaseModel):
    name: str
    description: str
    technologies: list[str] = []
    url: Optional[str] = None
    highlights: list[str] = []


class ExperienceItem(BaseModel):
    company: str
    title: str
    type: Optional[str] = "job"  # job or internship
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    description: str
    highlights: list[str] = []
    technologies: list[str] = []


class EducationItem(BaseModel):
    institution: str
    degree: str
    field: str
    start_date: Optional[str] = None
    end_date: Optional[str] = None
    gpa: Optional[str] = None


class ResearchPaperItem(BaseModel):
    title: str
    description: Optional[str] = None


class ParsedResume(BaseModel):
    skills: list[SkillItem] = []
    projects: list[ProjectItem] = []
    experience: list[ExperienceItem] = []
    education: list[EducationItem] = []
    certifications: list[str] = []
    research_papers: list[ResearchPaperItem] = []
    achievements: list[str] = []
    summary: Optional[str] = None


class ResumeResponse(BaseModel):
    id: UUID
    file_name: str
    file_url: str
    is_primary: bool
    skills: Optional[list] = None
    projects: Optional[list] = None
    experience: Optional[list] = None
    education: Optional[list] = None
    certifications: Optional[list] = None
    research_papers: Optional[list] = None
    achievements: Optional[list] = None
    summary: Optional[str] = None
    parsed_at: Optional[datetime] = None
    created_at: datetime

    model_config = {"from_attributes": True}
