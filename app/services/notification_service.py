import logging
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.models.recording import Notification
from app.models.user import User

logger = logging.getLogger(__name__)


class NotificationService:
    @staticmethod
    async def send_notification(
        db: AsyncSession,
        user_id: str,
        title: str,
        message: str,
        type: str = "info",
        link: Optional[str] = None
    ) -> Notification:
        """Create an in-app notification and simulate sending email/push notification."""
        notification = Notification(
            user_id=user_id,
            title=title,
            message=message,
            type=type,
            link=link
        )
        db.add(notification)
        await db.commit()
        await db.refresh(notification)

        # Simulate Email notification logging
        user_res = await db.execute(select(User.email).where(User.id == user_id))
        user_email = user_res.scalar_one_or_none()
        if user_email:
            logger.info(f"[EMAIL NOTIFICATION DISPATCH] To: {user_email} | Title: '{title}' | Message: '{message}'")

        return notification

    @staticmethod
    async def get_user_notifications(db: AsyncSession, user_id: str, limit: int = 20) -> list[Notification]:
        result = await db.execute(
            select(Notification)
            .where(Notification.user_id == user_id)
            .order_by(Notification.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    @staticmethod
    async def mark_as_read(db: AsyncSession, notification_id: str, user_id: str) -> bool:
        result = await db.execute(
            update(Notification)
            .where(Notification.id == notification_id, Notification.user_id == user_id)
            .values(is_read=True)
        )
        await db.commit()
        return result.rowcount > 0


notification_service = NotificationService()
