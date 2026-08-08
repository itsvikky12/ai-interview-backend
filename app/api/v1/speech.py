from fastapi import APIRouter, UploadFile, File, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.ai.openai_client import transcribe_audio
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/speech", tags=["Speech"])


@router.post("/transcribe")
async def transcribe_speech(
    audio: UploadFile = File(...),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Accepts a WebM/WAV/OGG audio blob and returns the transcribed text
    using OpenAI Whisper (falls back to a mock if no API key).
    """
    audio_bytes = await audio.read()
    logger.info("transcribe_request", user_id=str(user.id), size_bytes=len(audio_bytes))

    if len(audio_bytes) < 100:
        return {"transcript": "", "words": 0}

    text = await transcribe_audio(audio_bytes)
    word_count = len(text.split()) if text.strip() else 0

    logger.info("transcribe_result", user_id=str(user.id), words=word_count)
    return {"transcript": text.strip(), "words": word_count}
