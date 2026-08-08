import os
from datetime import datetime, timedelta, timezone
from sqlalchemy import select, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import async_session
from app.models.recording import InterviewRecording
from app.models.interview import Interview
from app.utils.logger import get_logger

logger = get_logger(__name__)


class CleanupService:
    @staticmethod
    async def run_7day_recording_cleanup() -> dict:
        """
        Deletes video recordings that were created more than 7 days ago.
        Cleans up physical files and updates DB records.
        """
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=7)
        deleted_count = 0
        freed_bytes = 0

        async with async_session() as db:
            try:
                stmt = select(InterviewRecording).where(InterviewRecording.created_at < cutoff_date)
                result = await db.execute(stmt)
                recordings = result.scalars().all()

                for rec in recordings:
                    # Remove file if local path exists
                    if rec.storage_path and os.path.exists(rec.storage_path):
                        try:
                            freed_bytes += os.path.getsize(rec.storage_path)
                            os.remove(rec.storage_path)
                        except Exception as e:
                            logger.error(f"Failed to delete file {rec.storage_path}: {e}")

                    # Nullify recording_url on interview if matched
                    int_stmt = select(Interview).where(Interview.id == rec.interview_id)
                    int_res = await db.execute(int_stmt)
                    interview = int_res.scalar_one_or_none()
                    if interview and interview.recording_url == rec.recording_url:
                        interview.recording_url = None

                    await db.delete(rec)
                    deleted_count += 1

                await db.commit()
                logger.info(f"7-day retention cleanup finished. Deleted {deleted_count} recordings, freed {freed_bytes} bytes.")
                return {"deleted_count": deleted_count, "freed_bytes": freed_bytes}
            except Exception as e:
                await db.rollback()
                logger.error(f"Error during 7-day recording cleanup: {e}")
                return {"error": str(e), "deleted_count": 0, "freed_bytes": 0}
