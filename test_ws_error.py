import asyncio
from uuid import uuid4
from datetime import datetime, timezone
from app.database import async_session
from app.services.interview_service import InterviewService
from app.utils.redis_client import get_redis, RedisCache

async def main():
    async with async_session() as db:
        redis = await get_redis()
        cache = RedisCache(redis)
        iv_service = InterviewService(db, cache)
        
        # Get first interview
        from sqlalchemy import select
        from app.models.interview import Interview, InterviewStatus, InterviewPhase
        result = await db.execute(select(Interview))
        interview = result.scalars().first()
        
        if not interview:
            print("No interview found")
            return
            
        print(f"Found interview {interview.id} for user {interview.user_id}")
        
        try:
            # Replicate what end event does
            iv_service = InterviewService(db, cache)
            fetched_interview = await iv_service.get_interview(interview.id, interview.user_id)
            fetched_interview.status = InterviewStatus.COMPLETED
            fetched_interview.current_phase = InterviewPhase.COMPLETED
            fetched_interview.completed_at = datetime.now(timezone.utc)
            await db.commit()
            print("Success!")
        except Exception as e:
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(main())
