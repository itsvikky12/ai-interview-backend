import uuid
import enum
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import String, DateTime, Float, Integer, Boolean, ForeignKey, Enum as SAEnum, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class ProblemDifficulty(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class SubmissionStatus(str, enum.Enum):
    ACCEPTED = "accepted"
    WRONG_ANSWER = "wrong_answer"
    TIME_LIMIT_EXCEEDED = "time_limit_exceeded"
    MEMORY_LIMIT_EXCEEDED = "memory_limit_exceeded"
    COMPILATION_ERROR = "compilation_error"
    RUNTIME_ERROR = "runtime_error"


class TestCaseType(str, enum.Enum):
    SAMPLE = "sample"
    BOUNDARY = "boundary"
    NULL_CASE = "null_case"
    LARGE_DATA = "large_data"
    STRESS = "stress"
    RANDOM = "random"
    PERFORMANCE = "performance"
    INVALID_INPUT = "invalid_input"


class CodingProblem(Base):
    __tablename__ = "coding_problems"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    difficulty: Mapped[ProblemDifficulty] = mapped_column(SAEnum(ProblemDifficulty), default=ProblemDifficulty.EASY, index=True)
    category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)
    company_tags: Mapped[Optional[Any]] = mapped_column(JSON)  # List of company names
    problem_statement: Mapped[str] = mapped_column(Text, nullable=False)
    input_format: Mapped[Optional[str]] = mapped_column(Text)
    output_format: Mapped[Optional[str]] = mapped_column(Text)
    constraints: Mapped[Optional[str]] = mapped_column(Text)
    examples: Mapped[Optional[Any]] = mapped_column(JSON)  # List of {input, output, explanation}
    hints: Mapped[Optional[Any]] = mapped_column(JSON)  # List of strings
    expected_time_complexity: Mapped[Optional[str]] = mapped_column(String(100))
    expected_space_complexity: Mapped[Optional[str]] = mapped_column(String(100))
    editorial_solution: Mapped[Optional[str]] = mapped_column(Text)
    ai_explanation: Mapped[Optional[str]] = mapped_column(Text)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    test_cases: Mapped[list["CodingTestCase"]] = relationship(back_populates="problem", cascade="all, delete-orphan")
    language_templates: Mapped[list["LanguageTemplate"]] = relationship(back_populates="problem", cascade="all, delete-orphan")


class LanguageTemplate(Base):
    __tablename__ = "language_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    problem_id: Mapped[str] = mapped_column(String(36), ForeignKey("coding_problems.id", ondelete="CASCADE"), nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False)  # python, java, cpp, javascript, go, rust, etc.
    starter_code: Mapped[str] = mapped_column(Text, nullable=False)
    boilerplate_code: Mapped[Optional[str]] = mapped_column(Text)
    compiler_version: Mapped[Optional[str]] = mapped_column(String(50))

    problem: Mapped["CodingProblem"] = relationship(back_populates="language_templates")


class CodingTestCase(Base):
    __tablename__ = "coding_test_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    problem_id: Mapped[str] = mapped_column(String(36), ForeignKey("coding_problems.id", ondelete="CASCADE"), nullable=False, index=True)
    input_data: Mapped[str] = mapped_column(Text, nullable=False)
    expected_output: Mapped[str] = mapped_column(Text, nullable=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    explanation: Mapped[Optional[str]] = mapped_column(Text)
    memory_limit_mb: Mapped[float] = mapped_column(Float, default=256.0)
    time_limit_ms: Mapped[int] = mapped_column(Integer, default=3000)
    test_type: Mapped[TestCaseType] = mapped_column(SAEnum(TestCaseType), default=TestCaseType.SAMPLE)
    order_index: Mapped[int] = mapped_column(Integer, default=0)

    problem: Mapped["CodingProblem"] = relationship(back_populates="test_cases")


class CodingSubmission(Base):
    __tablename__ = "coding_submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    interview_id: Mapped[str] = mapped_column(String(36), ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True)
    problem_id: Mapped[str] = mapped_column(String(36), ForeignKey("coding_problems.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    source_code: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[SubmissionStatus] = mapped_column(SAEnum(SubmissionStatus), default=SubmissionStatus.WRONG_ANSWER, index=True)
    passed_test_cases: Mapped[int] = mapped_column(Integer, default=0)
    total_test_cases: Mapped[int] = mapped_column(Integer, default=0)
    runtime_ms: Mapped[float] = mapped_column(Float, default=0.0)
    memory_mb: Mapped[float] = mapped_column(Float, default=0.0)
    compilation_log: Mapped[Optional[str]] = mapped_column(Text)
    browser_info: Mapped[Optional[str]] = mapped_column(String(255))
    device_info: Mapped[Optional[str]] = mapped_column(String(255))
    ip_address: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    interview: Mapped["Interview"] = relationship()
    problem: Mapped["CodingProblem"] = relationship()
    user: Mapped["User"] = relationship()
    submission_results: Mapped[list["SubmissionResult"]] = relationship(back_populates="submission", cascade="all, delete-orphan")
    ai_review: Mapped["AICodeReview"] = relationship(back_populates="submission", uselist=False, cascade="all, delete-orphan")


class SubmissionResult(Base):
    __tablename__ = "submission_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    submission_id: Mapped[str] = mapped_column(String(36), ForeignKey("coding_submissions.id", ondelete="CASCADE"), nullable=False, index=True)
    test_case_id: Mapped[str] = mapped_column(String(36), ForeignKey("coding_test_cases.id", ondelete="CASCADE"), nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, default=False)
    actual_output: Mapped[Optional[str]] = mapped_column(Text)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    runtime_ms: Mapped[float] = mapped_column(Float, default=0.0)
    memory_mb: Mapped[float] = mapped_column(Float, default=0.0)

    submission: Mapped["CodingSubmission"] = relationship(back_populates="submission_results")
    test_case: Mapped["CodingTestCase"] = relationship()


class AICodeReview(Base):
    __tablename__ = "ai_code_reviews"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    submission_id: Mapped[str] = mapped_column(String(36), ForeignKey("coding_submissions.id", ondelete="CASCADE"), nullable=False, unique=True)
    correctness_score: Mapped[float] = mapped_column(Float, default=0.0)
    time_complexity_rating: Mapped[float] = mapped_column(Float, default=0.0)
    space_complexity_rating: Mapped[float] = mapped_column(Float, default=0.0)
    code_quality_score: Mapped[float] = mapped_column(Float, default=0.0)
    optimization_score: Mapped[float] = mapped_column(Float, default=0.0)
    style_score: Mapped[float] = mapped_column(Float, default=0.0)
    overall_rating: Mapped[float] = mapped_column(Float, default=0.0)
    detected_time_complexity: Mapped[Optional[str]] = mapped_column(String(100))
    detected_space_complexity: Mapped[Optional[str]] = mapped_column(String(100))
    strengths: Mapped[Optional[Any]] = mapped_column(JSON)
    weaknesses: Mapped[Optional[Any]] = mapped_column(JSON)
    optimization_suggestions: Mapped[Optional[Any]] = mapped_column(JSON)
    interview_feedback: Mapped[Optional[str]] = mapped_column(Text)
    refactored_code: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    submission: Mapped["CodingSubmission"] = relationship(back_populates="ai_review")


class CodingScore(Base):
    __tablename__ = "coding_scores"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    interview_id: Mapped[str] = mapped_column(String(36), ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, unique=True)
    correctness_component: Mapped[float] = mapped_column(Float, default=0.0)  # 50%
    time_complexity_component: Mapped[float] = mapped_column(Float, default=0.0)  # 15%
    space_complexity_component: Mapped[float] = mapped_column(Float, default=0.0)  # 10%
    code_quality_component: Mapped[float] = mapped_column(Float, default=0.0)  # 10%
    optimization_component: Mapped[float] = mapped_column(Float, default=0.0)  # 10%
    style_component: Mapped[float] = mapped_column(Float, default=0.0)  # 5%
    total_coding_score: Mapped[float] = mapped_column(Float, default=0.0)
    technical_rating: Mapped[str] = mapped_column(String(100), default="COMPETENT")
    overall_performance_summary: Mapped[Optional[str]] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    interview: Mapped["Interview"] = relationship()


class CodingSession(Base):
    __tablename__ = "coding_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    interview_id: Mapped[str] = mapped_column(String(36), ForeignKey("interviews.id", ondelete="CASCADE"), nullable=False, index=True)
    problem_id: Mapped[str] = mapped_column(String(36), ForeignKey("coding_problems.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    active_code: Mapped[Optional[str]] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(50), default="python")
    warning_count: Mapped[int] = mapped_column(Integer, default=0)
    violations_log: Mapped[Optional[Any]] = mapped_column(JSON)
    keystroke_events: Mapped[Optional[Any]] = mapped_column(JSON)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    interview: Mapped["Interview"] = relationship()
    problem: Mapped["CodingProblem"] = relationship()
    user: Mapped["User"] = relationship()


class CompanyAssessmentTemplate(Base):
    __tablename__ = "company_assessment_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    company_name: Mapped[str] = mapped_column(String(100), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)
    easy_count: Mapped[int] = mapped_column(Integer, default=1)
    medium_count: Mapped[int] = mapped_column(Integer, default=1)
    hard_count: Mapped[int] = mapped_column(Integer, default=1)
    allowed_languages: Mapped[Optional[Any]] = mapped_column(JSON)
    time_limit_minutes: Mapped[int] = mapped_column(Integer, default=60)
    anti_cheat_config: Mapped[Optional[Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
