from pydantic_settings import BaseSettings
from pydantic import model_validator
from functools import lru_cache
from typing import Optional
import warnings


_INSECURE_DEFAULT_KEY = "change-this-to-a-real-secret-key-in-production"


class Settings(BaseSettings):
    APP_NAME: str = "AI Interview Platform"
    APP_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/ai_interview"
    DATABASE_SYNC_URL: str = "postgresql://postgres:postgres@localhost:5432/ai_interview"

    # Redis
    REDIS_URL: str = "redis://localhost:6379/0"

    # JWT
    JWT_SECRET_KEY: str = _INSECURE_DEFAULT_KEY
    JWT_ALGORITHM: str = "HS256"
    JWT_ACCESS_TOKEN_EXPIRE_MINUTES: int = 60
    JWT_REFRESH_TOKEN_EXPIRE_DAYS: int = 7

    # OpenAI
    OPENAI_API_KEY: str = ""
    OPENAI_MODEL: str = "gpt-4o"
    OPENAI_WHISPER_MODEL: str = "whisper-1"

    # Cloudflare R2 / AWS S3 / MinIO Storage
    STORAGE_PROVIDER: str = "r2"  # r2, s3, minio, local
    STORAGE_ENDPOINT_URL: Optional[str] = None  # e.g., "https://<account_id>.r2.cloudflarestorage.com"
    AWS_ACCESS_KEY_ID: str = ""
    AWS_SECRET_ACCESS_KEY: str = ""
    AWS_S3_BUCKET: str = "ai-interview-media"
    AWS_S3_REGION: str = "auto"
    R2_PUBLIC_URL: Optional[str] = None  # e.g., "https://pub-xxx.r2.dev" or custom domain
    RECORDING_RETENTION_DAYS: int = 7
    MEDIA_ROOT: str = "./media"

    # Cloudinary fallback
    CLOUDINARY_URL: Optional[str] = None

    # Rate limiting
    RATE_LIMIT_PER_MINUTE: int = 60

    # Interview settings
    INTERVIEW_TOTAL_MINUTES: int = 40
    INTRO_MINUTES: int = 5
    TECHNICAL_MINUTES: int = 20
    SYSTEM_DESIGN_MINUTES: int = 10
    HR_MINUTES: int = 5

    # CORS
    CORS_ORIGINS: list[str] = ["http://localhost:3000", "http://localhost:3001"]

    model_config = {"env_file": ".env", "extra": "ignore"}

    @model_validator(mode="after")
    def _check_security(self) -> "Settings":
        if self.DATABASE_URL.startswith("postgres://"):
            self.DATABASE_URL = self.DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
        elif self.DATABASE_URL.startswith("postgresql://") and "+asyncpg" not in self.DATABASE_URL:
            self.DATABASE_URL = self.DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

        if self.DATABASE_SYNC_URL.startswith("postgres://"):
            self.DATABASE_SYNC_URL = self.DATABASE_SYNC_URL.replace("postgres://", "postgresql://", 1)

        if not self.DEBUG and self.JWT_SECRET_KEY == _INSECURE_DEFAULT_KEY:
            raise ValueError(
                "JWT_SECRET_KEY must be set to a secure value in production. "
                "Set it in your .env file or environment variables."
            )
        if not self.DEBUG and self.JWT_SECRET_KEY and len(self.JWT_SECRET_KEY) < 32:
            warnings.warn("JWT_SECRET_KEY is shorter than 32 characters — consider using a longer key.")
        return self


@lru_cache()
def get_settings() -> Settings:
    return Settings()
