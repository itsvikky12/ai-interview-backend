from __future__ import annotations
from datetime import datetime, timedelta, timezone
from uuid import UUID
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from fastapi import HTTPException, status, Request

from app.models.user import User, UserRole
from app.models.audit_log import AuditLog
from app.schemas.auth import RegisterRequest, LoginRequest, TokenResponse, ChangePasswordRequest
from app.utils.security import hash_password, verify_password, create_access_token, create_refresh_token, decode_token
from app.utils.logger import get_logger

logger = get_logger(__name__)


class AuthService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def log_audit(
        self,
        action: str,
        user_id: str | None = None,
        admin_email: str = "system",
        details: dict | None = None,
        ip_address: str | None = None,
        user_agent: str | None = None,
    ):
        audit = AuditLog(
            user_id=user_id,
            admin_email=admin_email,
            action=action,
            details=details or {},
            ip_address=ip_address,
            user_agent=user_agent,
        )
        self.db.add(audit)
        await self.db.commit()

    async def register(self, data: RegisterRequest, request: Request | None = None) -> User:
        existing = await self.db.execute(select(User).where(User.email == data.email.lower()))
        if existing.scalar_one_or_none():
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already registered")

        user = User(
            email=data.email.lower(),
            hashed_password=hash_password(data.password),
            full_name=data.full_name,
            role=UserRole.STUDENT,
        )
        self.db.add(user)
        await self.db.flush()
        await self.db.refresh(user)
        await self.db.commit()

        client_ip = request.client.host if request and request.client else None
        user_agent = request.headers.get("user-agent") if request else None
        await self.log_audit(
            action="USER_REGISTERED",
            user_id=user.id,
            admin_email=user.email,
            details={"email": user.email, "role": user.role.value},
            ip_address=client_ip,
            user_agent=user_agent,
        )

        logger.info("user_registered", user_id=str(user.id), email=user.email)
        return user

    async def login(self, data: LoginRequest, request: Request | None = None) -> TokenResponse:
        client_ip = request.client.host if request and request.client else "127.0.0.1"
        user_agent = request.headers.get("user-agent") if request else "Unknown"

        result = await self.db.execute(select(User).where(func.lower(User.email) == data.email.lower()))
        user = result.scalars().first()



        if not user:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User does not exist. Please register."
            )

        now = datetime.now(timezone.utc)
        if user.locked_until and user.locked_until > now:
            minutes_left = int((user.locked_until - now).total_seconds() / 60) + 1
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail=f"Account is temporarily locked due to multiple failed login attempts. Please try again in {minutes_left} minutes."
            )

        if not verify_password(data.password, user.hashed_password):
            user.failed_login_attempts = (user.failed_login_attempts or 0) + 1
            if user.failed_login_attempts >= 5:
                user.locked_until = now + timedelta(minutes=15)
                await self.db.commit()
                await self.log_audit(
                    action="ACCOUNT_LOCKED",
                    user_id=user.id,
                    admin_email=user.email,
                    details={"reason": "5 consecutive failed login attempts"},
                    ip_address=client_ip,
                    user_agent=user_agent,
                )
                raise HTTPException(
                    status_code=status.HTTP_423_LOCKED,
                    detail="Too many failed login attempts. Account locked for 15 minutes."
                )
            await self.db.commit()
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid email or password. Attempt {user.failed_login_attempts} of 5."
            )

        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

        # Reset failed attempts & record last login
        user.failed_login_attempts = 0
        user.locked_until = None
        user.last_login_at = now
        user.last_login_ip = client_ip
        await self.db.commit()

        token_data = {"sub": str(user.id), "email": user.email, "role": user.role.value}
        access_token = create_access_token(token_data)
        refresh_token = create_refresh_token(token_data)

        await self.log_audit(
            action="LOGIN_SUCCESS",
            user_id=user.id,
            admin_email=user.email,
            details={"role": user.role.value},
            ip_address=client_ip,
            user_agent=user_agent,
        )

        logger.info("user_logged_in", user_id=str(user.id))
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            must_change_password=user.must_change_password,
            role=user.role.value,
            email=user.email,
            full_name=user.full_name,
        )

    async def change_password(self, user: User, data: ChangePasswordRequest) -> dict:
        if not verify_password(data.old_password, user.hashed_password):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Current password is incorrect")

        user.hashed_password = hash_password(data.new_password)
        user.must_change_password = False
        await self.db.commit()

        await self.log_audit(
            action="PASSWORD_CHANGED",
            user_id=user.id,
            admin_email=user.email,
            details={"self_changed": True},
        )
        return {"message": "Password changed successfully"}

    async def refresh_tokens(self, refresh_token: str) -> TokenResponse:
        payload = decode_token(refresh_token)
        if not payload or payload.get("type") != "refresh":
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid refresh token")

        user_id = payload.get("sub")
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()

        if not user or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")

        token_data = {"sub": str(user.id), "email": user.email, "role": user.role.value}
        new_access = create_access_token(token_data)
        new_refresh = create_refresh_token(token_data)

        return TokenResponse(
            access_token=new_access,
            refresh_token=new_refresh,
            must_change_password=user.must_change_password,
            role=user.role.value,
            email=user.email,
            full_name=user.full_name,
        )

    async def get_user_by_id(self, user_id: str) -> User:
        result = await self.db.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
        return user
