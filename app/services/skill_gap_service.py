from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.models.interview import Interview
from app.models.resume import Resume
from app.models.response import Response
from app.ai.response_evaluator import analyze_skill_gaps
from app.utils.logger import get_logger

logger = get_logger(__name__)


class SkillGapService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def analyze(self, interview_id: UUID) -> dict:
        result = await self.db.execute(select(Interview).where(Interview.id == str(interview_id)))
        interview = result.scalar_one_or_none()
        if not interview:
            return {}

        skills = []
        if interview.resume_id:
            res = await self.db.execute(select(Resume).where(Resume.id == interview.resume_id))
            resume = res.scalar_one_or_none()
            if resume and resume.skills:
                skills = resume.skills if isinstance(resume.skills, list) else []

        responses = await self.db.execute(
            select(Response)
            .where(Response.interview_id == str(interview_id))
            .options(selectinload(Response.question))
        )
        response_list = list(responses.scalars().all())

        performance = {
            "average_score": sum(r.score or 0 for r in response_list) / max(len(response_list), 1),
            "total_questions": len(response_list),
            "strong_areas": [r.question.topic for r in response_list if r.score and r.score >= 7.0 and r.question and r.question.topic],
            "weak_areas": [r.question.topic for r in response_list if r.score and r.score < 5.0 and r.question and r.question.topic],
        }

        analysis = await analyze_skill_gaps(
            target_role=interview.target_role,
            skills=skills,
            performance=performance,
        )

        logger.info("skill_gap_analyzed", interview_id=str(interview_id))
        return analysis
