from __future__ import annotations
from uuid import UUID
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from fastapi import HTTPException, status

from app.models.resume import Resume
from app.ai.resume_parser import parse_resume
from app.services.storage_service import StorageService
from app.utils.logger import get_logger

logger = get_logger(__name__)


class ResumeService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.storage = StorageService()

    async def upload_and_parse(self, user_id: UUID, file_bytes: bytes, filename: str) -> Resume:
        ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
        if ext not in ("pdf", "docx", "doc"):
            raise HTTPException(status_code=422, detail="Only PDF and DOCX files are supported")

        file_url = await self.storage.upload_file(file_bytes, filename, folder="resumes")

        raw_text, parsed = await parse_resume(file_bytes, ext)

        # Unset other primary resumes
        await self.db.execute(
            update(Resume).where(Resume.user_id == user_id).values(is_primary=False)
        )

        resume = Resume(
            user_id=user_id,
            file_url=file_url,
            file_name=filename,
            raw_text=raw_text,
            skills=[s.model_dump() for s in parsed.skills],
            projects=[p.model_dump() for p in parsed.projects],
            experience=[e.model_dump() for e in parsed.experience],
            education=[e.model_dump() for e in parsed.education],
            certifications=parsed.certifications,
            research_papers=[r.model_dump() for r in parsed.research_papers],
            achievements=parsed.achievements,
            summary=parsed.summary,
            is_primary=True,
            parsed_at=datetime.now(timezone.utc),
        )
        self.db.add(resume)
        await self.db.flush()
        await self.db.refresh(resume)
        await self.db.commit()

        logger.info("resume_uploaded", user_id=str(user_id), resume_id=str(resume.id))
        return resume

    async def get_resumes(self, user_id: UUID) -> list[Resume]:
        result = await self.db.execute(
            select(Resume).where(Resume.user_id == str(user_id)).order_by(Resume.created_at.desc())
        )
        return list(result.scalars().all())

    async def get_primary_resume(self, user_id: UUID) -> Resume | None:
        result = await self.db.execute(
            select(Resume).where(Resume.user_id == str(user_id), Resume.is_primary == True)
        )
        return result.scalar_one_or_none()

    async def get_resume_by_id(self, resume_id: UUID, user_id: UUID) -> Resume:
        result = await self.db.execute(
            select(Resume).where(Resume.id == str(resume_id), Resume.user_id == str(user_id))
        )
        resume = result.scalar_one_or_none()
        if not resume:
            raise HTTPException(status_code=404, detail="Resume not found")
        return resume

    async def delete_resume(self, resume_id: UUID, user_id: UUID) -> None:
        resume = await self.get_resume_by_id(resume_id, user_id)
        # Best-effort file cleanup — storage errors must NOT block DB deletion
        try:
            await self.storage.delete_file(resume.file_url)
        except Exception as e:
            logger.warning("resume_file_delete_failed", resume_id=str(resume_id), error=str(e))
        # Always delete the DB record regardless of storage outcome
        await self.db.delete(resume)
        await self.db.commit()
        logger.info("resume_deleted", user_id=str(user_id), resume_id=str(resume_id))
