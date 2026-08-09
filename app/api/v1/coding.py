import uuid
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.models.coding import CodingProblem, CodingTestCase, LanguageTemplate, CodingSession
from app.services.coding_service import CodingService
from app.services.problem_seed_service import seed_coding_problems
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/coding", tags=["Coding Assessment"])


class RunCodeRequest(BaseModel):
    problem_id: str
    source_code: str
    language: str


class SubmitCodeRequest(BaseModel):
    interview_id: str
    problem_id: str
    source_code: str
    language: str
    browser_info: Optional[str] = "Standard Browser"


class ProctorWarningRequest(BaseModel):
    interview_id: str
    event_type: str
    details: Optional[str] = None


@router.get("/problems")
async def list_problems(
    category: Optional[str] = None,
    difficulty: Optional[str] = None,
    search: Optional[str] = None,
    company_tag: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """List coding problems with search and topic filtering."""
    # Ensure seed problems exist
    await seed_coding_problems(db)

    service = CodingService(db)
    problems = await service.get_problems(
        category=category,
        difficulty=difficulty,
        search=search,
        company_tag=company_tag,
        limit=limit,
        offset=offset
    )

    return [
        {
            "id": p.id,
            "title": p.title,
            "slug": p.slug,
            "difficulty": p.difficulty,
            "category": p.category,
            "company_tags": p.company_tags or [],
            "expected_time_complexity": p.expected_time_complexity,
            "expected_space_complexity": p.expected_space_complexity,
        }
        for p in problems
    ]


@router.get("/problems/{problem_id}")
async def get_problem(
    problem_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Get coding problem details, visible test cases, and language templates."""
    service = CodingService(db)
    problem = await service.get_problem_by_id(problem_id)
    if not problem:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Problem not found")

    # Fetch visible test cases
    tc_res = await db.execute(
        select(CodingTestCase)
        .where(CodingTestCase.problem_id == problem_id, CodingTestCase.is_hidden == False)
        .order_by(CodingTestCase.order_index.asc())
    )
    visible_test_cases = tc_res.scalars().all()

    # Fetch templates
    tmpl_res = await db.execute(
        select(LanguageTemplate).where(LanguageTemplate.problem_id == problem_id)
    )
    templates = tmpl_res.scalars().all()

    return {
        "id": problem.id,
        "title": problem.title,
        "slug": problem.slug,
        "difficulty": problem.difficulty,
        "category": problem.category,
        "company_tags": problem.company_tags or [],
        "problem_statement": problem.problem_statement,
        "input_format": problem.input_format,
        "output_format": problem.output_format,
        "constraints": problem.constraints,
        "examples": problem.examples or [],
        "hints": problem.hints or [],
        "expected_time_complexity": problem.expected_time_complexity,
        "expected_space_complexity": problem.expected_space_complexity,
        "visible_test_cases": [
            {
                "id": tc.id,
                "input": tc.input_data,
                "expected_output": tc.expected_output,
                "explanation": tc.explanation
            }
            for tc in visible_test_cases
        ],
        "language_templates": {
            t.language: {
                "starter_code": t.starter_code,
                "compiler_version": t.compiler_version
            }
            for t in templates
        }
    }


@router.get("/interview/{interview_id}/problem")
async def get_interview_coding_problem(
    interview_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Dynamically assign or fetch the coding problem for an ongoing interview."""
    from app.models.interview import Interview
    from app.models.user import UserRole

    # Verify interview ownership
    iv_res = await db.execute(select(Interview).where(Interview.id == interview_id))
    interview = iv_res.scalar_one_or_none()
    if not interview:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Interview not found")
    if current_user.role != UserRole.ADMIN and interview.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    await seed_coding_problems(db)
    service = CodingService(db)

    # Check if a session already exists
    sess_res = await db.execute(select(CodingSession).where(CodingSession.interview_id == interview_id))
    existing_session = sess_res.scalars().first()

    if existing_session:
        problem = await service.get_problem_by_id(existing_session.problem_id)
    else:
        problem = await service.get_adaptive_problem_for_interview(interview_id)
        # Create session tracking record
        new_session = CodingSession(
            id=str(uuid.uuid4()),
            interview_id=interview_id,
            problem_id=problem.id,
            user_id=current_user.id,
            language="python",
            warning_count=0,
            violations_log=[]
        )
        db.add(new_session)
        await db.commit()

    return await get_problem(problem.id, db, current_user)


@router.post("/run")
async def run_code(
    req: RunCodeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Execute code against visible test cases."""
    service = CodingService(db)
    return await service.run_code(
        problem_id=req.problem_id,
        source_code=req.source_code,
        language=req.language
    )


@router.post("/submit")
async def submit_code(
    req: SubmitCodeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Submit code for full hidden test case evaluation & AI review."""
    service = CodingService(db)
    client_ip = request.client.host if request.client else "127.0.0.1"
    
    return await service.submit_code(
        interview_id=req.interview_id,
        problem_id=req.problem_id,
        user_id=current_user.id,
        source_code=req.source_code,
        language=req.language,
        browser_info=req.browser_info or "Web Browser",
        ip_address=client_ip
    )


@router.post("/proctor/warning")
async def log_proctor_warning(
    req: ProctorWarningRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Log security proctor warning. Automatically triggers auto-submit on 3 warnings."""
    sess_res = await db.execute(select(CodingSession).where(CodingSession.interview_id == req.interview_id))
    session = sess_res.scalar_one_or_none()

    if not session:
        return {"warning_count": 1, "auto_submitted": False}

    session.warning_count += 1
    v_log = session.violations_log or []
    v_log.append({
        "event_type": req.event_type,
        "details": req.details,
        "timestamp": str(datetime.now(timezone.utc))
    })
    session.violations_log = v_log
    await db.commit()

    auto_submitted = session.warning_count >= 3
    return {
        "warning_count": session.warning_count,
        "auto_submitted": auto_submitted,
        "message": "3 Proctor warnings exceeded. Assessment auto-submitted." if auto_submitted else "Warning recorded."
    }
