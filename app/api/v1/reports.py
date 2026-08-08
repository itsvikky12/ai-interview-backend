from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.database import get_db
from app.schemas.report import ReportResponse
from app.services.report_service import ReportService
from app.services.interview_service import InterviewService
from app.dependencies import get_current_user, get_cache
from app.models.user import User
from app.models.interview import InterviewStatus

router = APIRouter(prefix="/reports", tags=["Reports"])


@router.post("/{interview_id}/generate", response_model=ReportResponse, status_code=201)
async def generate_report(
    interview_id: UUID,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache),
):
    # Verify user owns interview and it's completed
    iv_service = InterviewService(db, cache)
    interview = await iv_service.get_interview(interview_id, user.id)

    if interview.status not in (InterviewStatus.COMPLETED, InterviewStatus.FLAGGED):
        raise HTTPException(status_code=400, detail="Interview must be completed before generating a report")

    service = ReportService(db)
    report = await service.start_async_generation(interview_id, background_tasks)
    return report


@router.get("/{interview_id}", response_model=ReportResponse)
async def get_report(
    interview_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    cache=Depends(get_cache),
):
    iv_service = InterviewService(db, cache)
    await iv_service.get_interview(interview_id, user.id)

    service = ReportService(db)
    report = await service.get_report(interview_id)
    if not report:
        raise HTTPException(status_code=404, detail="Report not yet generated")
    return report
