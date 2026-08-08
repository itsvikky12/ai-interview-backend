import logging
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.recording import InterviewRecording, RecordingStatus
from app.services.recording_service import recording_service
from app.services.notification_service import notification_service

logger = logging.getLogger(__name__)


async def run_daily_retention_cleanup(db: AsyncSession) -> dict:
    """
    Scheduled job:
    1. Sends warning notification to users whose recordings expire in < 24 hours.
    2. Deletes media files & revokes URLs for recordings past expires_at (7 days).
    """
    now = datetime.now(timezone.utc)
    twenty_four_hours = now + timedelta(hours=24)

    # 1. 24-Hour Pre-Expiry Warnings
    warning_query = await db.execute(
        select(InterviewRecording).where(
            InterviewRecording.upload_status == RecordingStatus.READY,
            InterviewRecording.expires_at <= twenty_four_hours,
            InterviewRecording.expires_at > now,
            InterviewRecording.expiry_warning_sent == False
        )
    )
    expiring_soon = warning_query.scalars().all()
    warning_count = 0

    for rec in expiring_soon:
        await notification_service.send_notification(
            db,
            user_id=rec.student_id,
            title="Interview Recording Expiring Soon",
            message="Your interview recording will be permanently deleted in 24 hours according to our retention policy. Download it now if needed.",
            type="warning",
            link=f"/dashboard/recordings/{rec.id}"
        )
        rec.expiry_warning_sent = True
        warning_count += 1

    await db.commit()

    # 2. Automated Deletion Purge (Recordings expired > 7 days)
    expired_query = await db.execute(
        select(InterviewRecording).where(
            InterviewRecording.upload_status.in_([RecordingStatus.READY, RecordingStatus.PROCESSING]),
            InterviewRecording.expires_at <= now
        )
    )
    expired_recordings = expired_query.scalars().all()
    deleted_count = 0

    for rec in expired_recordings:
        try:
            await recording_service.delete_recording(
                db,
                recording_id=rec.id,
                actor_id="system_cron",
                actor_role="system",
                reason="Automated 7-day retention expiry cleanup"
            )
            deleted_count += 1
        except Exception as e:
            logger.error(f"Error purging expired recording {rec.id}: {e}")

    logger.info(f"[RETENTION CLEANUP] Task completed. Warnings Sent: {warning_count}, Expired Recordings Purged: {deleted_count}")
    return {"warnings_sent": warning_count, "purged_count": deleted_count}
