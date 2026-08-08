from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.database import get_db
from app.schemas.interview import InterviewCreate, InterviewResponse, InterviewListItem, AnswerSubmit, QuestionOut
from app.services.interview_service import InterviewService
from app.dependencies import get_current_user, get_cache
from app.models.user import User
from app.utils.redis_client import RedisCache

router = APIRouter(prefix="/interviews", tags=["Interviews"])


@router.post("/", response_model=InterviewResponse, status_code=201)
async def create_interview(
    data: InterviewCreate,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: RedisCache = Depends(get_cache),
):
    service = InterviewService(db, cache)
    interview = await service.create_interview(user.id, data.target_role, data.resume_id, data.language)
    return interview


@router.post("/{interview_id}/start")
async def start_interview(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: RedisCache = Depends(get_cache),
):
    service = InterviewService(db, cache)
    return await service.start_interview(interview_id, user.id)


@router.post("/{interview_id}/answer")
async def submit_answer(
    interview_id: UUID,
    data: AnswerSubmit,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: RedisCache = Depends(get_cache),
):
    service = InterviewService(db, cache)
    return await service.submit_answer(
        interview_id, user.id, data.question_id, data.answer_text, data.audio_url, data.duration_seconds,
    )


@router.get("/", response_model=list[InterviewListItem])
async def list_interviews(
    skip: int = Query(0, ge=0),
    limit: int = Query(20, ge=1, le=100),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: RedisCache = Depends(get_cache),
):
    service = InterviewService(db, cache)
    return await service.get_user_interviews(user.id, skip, limit)


@router.get("/{interview_id}", response_model=InterviewResponse)
async def get_interview(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: RedisCache = Depends(get_cache),
):
    service = InterviewService(db, cache)
    return await service.get_interview(interview_id, user.id)


from pydantic import BaseModel

class AssociateResumeRequest(BaseModel):
    resume_id: UUID

@router.post("/{interview_id}/associate_resume", response_model=InterviewResponse)
async def associate_resume(
    interview_id: UUID,
    data: AssociateResumeRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: RedisCache = Depends(get_cache),
):
    service = InterviewService(db, cache)
    return await service.associate_resume(interview_id, user.id, data.resume_id)


@router.get("/{interview_id}/questions", response_model=list[QuestionOut])
async def get_interview_questions(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache: RedisCache = Depends(get_cache),
):
    service = InterviewService(db, cache)
    await service.get_interview(interview_id, user.id)
    
    from sqlalchemy import select
    from app.models.question import Question
    result = await db.execute(
        select(Question)
        .where(Question.interview_id == str(interview_id))
        .order_by(Question.order_index)
    )
    questions = result.scalars().all()
    return questions


@router.get("/flow-rules/config")
async def get_interview_flow_config(
    difficulty: str = Query("easy", description="Round difficulty: easy, medium, or hard"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Returns Interview Question Flow Rules configuration according to difficulty round matrix:
    - Easy: 1 Easy SQL/MySQL (10 min) + 1 Medium DSA (20 min)
    - Medium: 1 Easy SQL/MySQL (10 min) + 1 Medium DSA (20 min)
    - Hard: 1 Hard DSA ONLY (30 min)
    """
    from app.services.interview_flow_service import InterviewFlowService
    flow_service = InterviewFlowService(db)
    return await flow_service.get_round_configuration(difficulty)

