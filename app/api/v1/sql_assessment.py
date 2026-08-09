import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update

from app.database import get_db
from app.dependencies import get_current_user, get_current_admin_user
from app.models.user import User
from app.models.sql_assessment import SqlProblem, SqlDifficulty, SqlTestCase, SqlSubmission, SqlSubmissionStatus
from app.models.system_setting import SystemSetting
from app.services.sql_seed_service import seed_sql_problems
from app.services.sql_sandbox_service import SqlSandboxService
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/sql", tags=["SQL Assessment"])


class RunSqlQueryRequest(BaseModel):
    problem_id: str
    submitted_sql: str


class SubmitSqlQueryRequest(BaseModel):
    problem_id: str
    submitted_sql: str
    interview_id: Optional[str] = None
    time_spent_seconds: Optional[int] = 0
    is_auto_submitted: Optional[bool] = False


class UpdateSqlAdminSettingsRequest(BaseModel):
    enable_medium_hard: bool


@router.get("/problems")
async def list_sql_problems(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    target_role: Optional[str] = None,
    search: Optional[str] = None,
    limit: int = 150,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List SQL assessment questions with topic, role, and search filters."""
    # Ensure seed questions exist
    await seed_sql_problems(db)

    # Check if admin enabled medium/hard questions
    setting_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "enable_medium_hard_sql"))
    setting = setting_res.scalar_one_or_none()
    enable_medium_hard = setting.value.get("enabled", False) if setting and setting.value else False

    query = select(SqlProblem).where(SqlProblem.is_active == True)

    if not enable_medium_hard and current_user.role != "admin":
        query = query.where(SqlProblem.difficulty == SqlDifficulty.EASY)

    if category:
        query = query.where(SqlProblem.category == category)
    if difficulty:
        query = query.where(SqlProblem.difficulty == difficulty)
    if search:
        query = query.where(
            SqlProblem.title.ilike(f"%{search}%") | 
            SqlProblem.question_id.ilike(f"%{search}%")
        )

    query = query.order_by(SqlProblem.question_id.asc()).offset(offset).limit(limit)
    res = await db.execute(query)
    problems = res.scalars().all()

    return [
        {
            "id": p.id,
            "question_id": p.question_id,
            "title": p.title,
            "slug": p.slug,
            "difficulty": p.difficulty,
            "category": p.category,
            "target_roles": p.target_roles or [],
            "starter_sql_template": p.starter_sql_template,
        }
        for p in problems
    ]


@router.get("/problems/{problem_id}")
async def get_sql_problem(
    problem_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get full details for a specific SQL problem, database schema, sample records, and visible Test Case 1."""
    res = await db.execute(select(SqlProblem).where((SqlProblem.id == problem_id) | (SqlProblem.question_id == problem_id)))
    problem = res.scalar_one_or_none()

    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SQL problem not found")

    # Fetch Test Case 1 (Visible)
    tc_res = await db.execute(
        select(SqlTestCase)
        .where(SqlTestCase.problem_id == problem.id, SqlTestCase.is_hidden == False)
        .order_by(SqlTestCase.test_case_number.asc())
    )
    visible_test_cases = tc_res.scalars().all()

    return {
        "id": problem.id,
        "question_id": problem.question_id,
        "title": problem.title,
        "slug": problem.slug,
        "difficulty": problem.difficulty,
        "category": problem.category,
        "target_roles": problem.target_roles or [],
        "problem_statement": problem.problem_statement,
        "database_schema_info": problem.database_schema_info,
        "sample_records": problem.sample_records,
        "expected_output_info": problem.expected_output_info,
        "explanation": problem.explanation,
        "starter_sql_template": problem.starter_sql_template,
        "visible_test_cases": [
            {
                "id": tc.id,
                "test_case_number": tc.test_case_number,
                "name": tc.name,
                "explanation": tc.explanation
            }
            for tc in visible_test_cases
        ]
    }


@router.post("/run")
async def run_sql_query(
    req: RunSqlQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Runs candidate SQL query against visible Test Case 1 sample database in real sandbox."""
    res = await db.execute(select(SqlProblem).where(SqlProblem.id == req.problem_id))
    problem = res.scalar_one_or_none()

    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SQL problem not found")

    # Fetch Test Case 1
    tc_res = await db.execute(
        select(SqlTestCase)
        .where(SqlTestCase.problem_id == problem.id, SqlTestCase.test_case_number == 1)
    )
    tc1 = tc_res.scalar_one_or_none()

    setup_sql = tc1.setup_sql if tc1 else ""
    sandbox_result = SqlSandboxService.execute_in_sandbox(setup_sql, req.submitted_sql)

    return sandbox_result


@router.post("/submit")
async def submit_sql_query(
    req: SubmitSqlQueryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Submits SQL query, evaluates across all 3 test cases, calculates score & AI review,
    and handles timer auto-submit.
    """
    res = await db.execute(select(SqlProblem).where(SqlProblem.id == req.problem_id))
    problem = res.scalar_one_or_none()

    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SQL problem not found")

    if req.interview_id:
        from app.models.interview import Interview
        from app.models.user import UserRole
        iv_res = await db.execute(select(Interview).where(Interview.id == req.interview_id))
        interview = iv_res.scalar_one_or_none()
        if not interview:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Associated interview not found")
        if current_user.role != UserRole.ADMIN and interview.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Fetch all 3 test cases
    tc_res = await db.execute(
        select(SqlTestCase)
        .where(SqlTestCase.problem_id == problem.id)
        .order_by(SqlTestCase.test_case_number.asc())
    )
    all_test_cases = tc_res.scalars().all()
    test_cases_list = [
        {
            "id": tc.id,
            "test_case_number": tc.test_case_number,
            "name": tc.name,
            "is_hidden": tc.is_hidden,
            "setup_sql": tc.setup_sql
        }
        for tc in all_test_cases
    ]

    # Evaluate submission in Sandbox engine
    eval_result = SqlSandboxService.evaluate_sql_submission(
        submitted_sql=req.submitted_sql,
        solution_sql=problem.solution_sql,
        test_cases=test_cases_list
    )

    submission_id = str(uuid.uuid4())
    sub = SqlSubmission(
        id=submission_id,
        interview_id=req.interview_id,
        problem_id=problem.id,
        user_id=current_user.id,
        submitted_sql=req.submitted_sql,
        status=SqlSubmissionStatus.ACCEPTED if eval_result["status"] == "ACCEPTED" else SqlSubmissionStatus.WRONG_ANSWER,
        passed_test_cases=eval_result["passed_test_cases"],
        total_test_cases=eval_result["total_test_cases"],
        execution_time_ms=eval_result["execution_time_ms"],
        score=eval_result["score"],
        scoring_breakdown=eval_result["scoring_breakdown"],
        quality_rating=eval_result["quality_rating"],
        ai_review=eval_result["ai_review"],
        is_auto_submitted=req.is_auto_submitted or False,
        time_spent_seconds=req.time_spent_seconds or 0
    )

    db.add(sub)
    await db.commit()

    return {
        "submission_id": sub.id,
        "status": sub.status,
        "passed_test_cases": sub.passed_test_cases,
        "total_test_cases": sub.total_test_cases,
        "execution_time_ms": sub.execution_time_ms,
        "score": sub.score,
        "scoring_breakdown": sub.scoring_breakdown,
        "quality_rating": sub.quality_rating,
        "is_auto_submitted": sub.is_auto_submitted,
        "test_case_results": eval_result["test_case_results"],
        "ai_review": eval_result["ai_review"]
    }


@router.get("/submissions/{submission_id}")
async def get_sql_submission(
    submission_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Fetch submission status, scores, and AI review."""
    res = await db.execute(select(SqlSubmission).where(SqlSubmission.id == submission_id))
    sub = res.scalar_one_or_none()

    if not sub:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Submission not found")

    if sub.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    return {
        "id": sub.id,
        "problem_id": sub.problem_id,
        "submitted_sql": sub.submitted_sql,
        "status": sub.status,
        "passed_test_cases": sub.passed_test_cases,
        "total_test_cases": sub.total_test_cases,
        "execution_time_ms": sub.execution_time_ms,
        "score": sub.score,
        "scoring_breakdown": sub.scoring_breakdown,
        "quality_rating": sub.quality_rating,
        "ai_review": sub.ai_review,
        "is_auto_submitted": sub.is_auto_submitted,
        "created_at": sub.created_at
    }


@router.get("/admin/settings")
async def get_sql_admin_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Admin endpoint to fetch SQL assessment configuration."""
    setting_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "enable_medium_hard_sql"))
    setting = setting_res.scalar_one_or_none()
    enable_medium_hard = setting.value.get("enabled", False) if setting and setting.value else False

    return {
        "enable_medium_hard": enable_medium_hard
    }


@router.put("/admin/settings")
async def update_sql_admin_settings(
    req: UpdateSqlAdminSettingsRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin_user)
):
    """Admin endpoint to enable/disable Medium and Hard SQL questions."""
    setting_res = await db.execute(select(SystemSetting).where(SystemSetting.key == "enable_medium_hard_sql"))
    setting = setting_res.scalar_one_or_none()

    if not setting:
        setting = SystemSetting(
            key="enable_medium_hard_sql",
            value={"enabled": req.enable_medium_hard},
            description="Toggle enabling Medium and Hard SQL questions in assessments"
        )
        db.add(setting)
    else:
        setting.value = {"enabled": req.enable_medium_hard}

    await db.commit()

    return {"message": "SQL settings updated successfully", "enable_medium_hard": req.enable_medium_hard}
