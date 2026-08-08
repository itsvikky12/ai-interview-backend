import uuid
import enum
from datetime import datetime, timezone
from typing import Any, Optional
from sqlalchemy import String, DateTime, Float, Integer, Boolean, ForeignKey, Enum as SAEnum, Text, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.database import Base


class SqlDifficulty(str, enum.Enum):
    EASY = "easy"
    MEDIUM = "medium"
    HARD = "hard"


class SqlSubmissionStatus(str, enum.Enum):
    ACCEPTED = "accepted"
    WRONG_ANSWER = "wrong_answer"
    SYNTAX_ERROR = "syntax_error"
    TIME_LIMIT_EXCEEDED = "time_limit_exceeded"
    EVALUATION_ERROR = "evaluation_error"


class SqlProblem(Base):
    __tablename__ = "sql_problems"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    question_id: Mapped[str] = mapped_column(String(50), unique=True, index=True, nullable=False)  # e.g., SQL-101
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    difficulty: Mapped[SqlDifficulty] = mapped_column(SAEnum(SqlDifficulty), default=SqlDifficulty.EASY, index=True)
    category: Mapped[str] = mapped_column(String(100), index=True, nullable=False)  # e.g., Aggregations, Joins, Filtering
    target_roles: Mapped[Optional[Any]] = mapped_column(JSON)  # List of target roles (e.g. Freshers, Data Analyst, Backend Developer)
    problem_statement: Mapped[str] = mapped_column(Text, nullable=False)
    database_schema_info: Mapped[Optional[Any]] = mapped_column(JSON)  # Schema metadata & table list
    sample_records: Mapped[Optional[Any]] = mapped_column(JSON)  # Dict of table_name -> list of sample dict rows
    expected_output_info: Mapped[Optional[Any]] = mapped_column(JSON)  # Description / array of expected rows
    explanation: Mapped[Optional[str]] = mapped_column(Text)
    starter_sql_template: Mapped[str] = mapped_column(Text, nullable=False)
    solution_sql: Mapped[str] = mapped_column(Text, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc)
    )

    test_cases: Mapped[list["SqlTestCase"]] = relationship(back_populates="problem", cascade="all, delete-orphan")
    submissions: Mapped[list["SqlSubmission"]] = relationship(back_populates="problem", cascade="all, delete-orphan")


class SqlTestCase(Base):
    __tablename__ = "sql_test_cases"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    problem_id: Mapped[str] = mapped_column(String(36), ForeignKey("sql_problems.id", ondelete="CASCADE"), nullable=False, index=True)
    test_case_number: Mapped[int] = mapped_column(Integer, nullable=False)  # 1, 2, 3
    name: Mapped[str] = mapped_column(String(100), nullable=False)  # "Test Case 1: Visible Sample Data", "Test Case 2: Hidden Dataset", "Test Case 3: Edge Case Dataset"
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    setup_sql: Mapped[str] = mapped_column(Text, nullable=False)  # DDL + INSERT statements for setup
    expected_result: Mapped[Optional[Any]] = mapped_column(JSON)  # [{col: val}] expected result set
    explanation: Mapped[Optional[str]] = mapped_column(Text)

    problem: Mapped["SqlProblem"] = relationship(back_populates="test_cases")


class SqlSubmission(Base):
    __tablename__ = "sql_submissions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    interview_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("interviews.id", ondelete="SET NULL"), nullable=True, index=True)
    problem_id: Mapped[str] = mapped_column(String(36), ForeignKey("sql_problems.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    submitted_sql: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[SqlSubmissionStatus] = mapped_column(SAEnum(SqlSubmissionStatus), default=SqlSubmissionStatus.WRONG_ANSWER, index=True)
    passed_test_cases: Mapped[int] = mapped_column(Integer, default=0)
    total_test_cases: Mapped[int] = mapped_column(Integer, default=3)
    execution_time_ms: Mapped[float] = mapped_column(Float, default=0.0)
    
    # SQL Scoring Weights: Correctness 70%, Optimization 15%, Syntax & Best Practices 10%, Speed 5%
    score: Mapped[float] = mapped_column(Float, default=0.0)
    scoring_breakdown: Mapped[Optional[Any]] = mapped_column(JSON)  # {correctness, optimization, syntax, speed}
    quality_rating: Mapped[str] = mapped_column(String(50), default="NEEDS_IMPROVEMENT")  # EXCELLENT, GOOD, NEEDS_IMPROVEMENT, POOR
    ai_review: Mapped[Optional[Any]] = mapped_column(JSON)  # Detailed AI review dict
    is_auto_submitted: Mapped[bool] = mapped_column(Boolean, default=False)
    time_spent_seconds: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    problem: Mapped["SqlProblem"] = relationship(back_populates="submissions")
    user: Mapped["User"] = relationship()
    interview: Mapped[Optional["Interview"]] = relationship()
