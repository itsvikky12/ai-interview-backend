from fastapi import APIRouter, Depends, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from uuid import UUID

from app.database import get_db
from app.schemas.resume import ResumeResponse
from app.services.resume_service import ResumeService
from app.dependencies import get_current_user
from app.models.user import User
from app.utils.validators import validate_file_extension, validate_file_size

router = APIRouter(prefix="/resumes", tags=["Resumes"])


@router.post("/upload", response_model=ResumeResponse, status_code=201)
async def upload_resume(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    validate_file_extension(file.filename or "", ["pdf", "docx", "doc"])
    file_bytes = await file.read()
    validate_file_size(len(file_bytes), max_mb=10)

    service = ResumeService(db)
    resume = await service.upload_and_parse(user.id, file_bytes, file.filename or "resume.pdf")
    return resume


@router.get("/", response_model=list[ResumeResponse])
async def list_resumes(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ResumeService(db)
    return await service.get_resumes(user.id)


@router.get("/{resume_id}", response_model=ResumeResponse)
async def get_resume(
    resume_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ResumeService(db)
    return await service.get_resume_by_id(resume_id, user.id)


@router.delete("/{resume_id}", status_code=204)
async def delete_resume(
    resume_id: UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    service = ResumeService(db)
    await service.delete_resume(resume_id, user.id)
