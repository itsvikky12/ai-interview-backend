from __future__ import annotations
import asyncio
import json
from uuid import UUID
from datetime import datetime, timezone
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import async_session
from app.utils.security import decode_token
from app.utils.redis_client import get_redis, RedisCache
from app.services.interview_service import InterviewService
from app.services.anti_cheat_service import AntiCheatService
from app.services.speech_service import SpeechAnalyzer
from app.ai.openai_client import transcribe_audio
from app.models.interview import InterviewStatus, InterviewPhase
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

# Sliding binary audio chunk cache (last 30 seconds of audio)
audio_buffers: dict[str, list[bytes]] = {}


class ConnectionManager:
    def __init__(self):
        self.active: dict[str, WebSocket] = {}

    async def connect(self, interview_id: str, ws: WebSocket):
        await ws.accept()
        self.active[interview_id] = ws

    def disconnect(self, interview_id: str):
        self.active.pop(interview_id, None)
        audio_buffers.pop(interview_id, None)

    async def send(self, interview_id: str, data: dict):
        ws = self.active.get(interview_id)
        if ws:
            await ws.send_json(data)


manager = ConnectionManager()


@router.websocket("/ws/interview/{interview_id}")
async def interview_websocket(websocket: WebSocket, interview_id: str):
    # Validate UUID format
    try:
        UUID(interview_id)
    except ValueError:
        await websocket.close(code=4002, reason="Invalid interview ID")
        return

    # Auth from query param
    token = websocket.query_params.get("token", "")
    payload = decode_token(token)
    if not payload or payload.get("type") != "access":
        await websocket.close(code=4001, reason="Unauthorized")
        return

    user_id = payload.get("sub")
    if not user_id:
        await websocket.close(code=4001, reason="Invalid token")
        return

    # Validate interview ownership (prevent BOLA/IDOR)
    async with async_session() as db:
        from app.models.interview import Interview
        from sqlalchemy import select
        result = await db.execute(
            select(Interview).where(Interview.id == str(interview_id), Interview.user_id == str(user_id))
        )
        interview = result.scalar_one_or_none()
        if not interview:
            await websocket.close(code=4003, reason="Unauthorized interview session")
            return

    await manager.connect(interview_id, websocket)
    logger.info("ws_connected", interview_id=interview_id, user_id=user_id)

    speech_analyzer = SpeechAnalyzer()

    # Per-connection transcript_update debounce timer
    transcript_debounce_task: asyncio.Task | None = None
    try:
        while True:
            # ── Receive either a text (JSON) or binary (raw audio) frame ──────────
            raw_message = await websocket.receive()
            if raw_message.get("type") == "websocket.disconnect":
                raise WebSocketDisconnect(code=raw_message.get("code", 1000))

            # ── Binary frame: raw audio chunk from browser MediaRecorder ──────────
            if raw_message.get("bytes") is not None:
                audio_bytes: bytes = raw_message["bytes"]
                if audio_bytes:
                    if interview_id not in audio_buffers:
                        audio_buffers[interview_id] = []
                    audio_buffers[interview_id].append(audio_bytes)
                    # Sliding window: keep last 30 seconds (60 chunks × 500ms)
                    if len(audio_buffers[interview_id]) > 60:
                        audio_buffers[interview_id].pop(0)
                    # No response needed — fire-and-forget cache update
                continue

            # ── Text frame: JSON control messages ────────────────────────────────
            raw_text = raw_message.get("text", "")
            if not raw_text:
                continue

            try:
                message = json.loads(raw_text)
            except json.JSONDecodeError:
                await manager.send(interview_id, {"type": "error", "data": {"message": "Invalid JSON"}})
                continue

            msg_type = message.get("type", "")
            msg_data = message.get("data", {})

            async with async_session() as db:
                redis_client = await get_redis()
                cache = RedisCache(redis_client)

                if msg_type == "start":
                    iv_service = InterviewService(db, cache)
                    result = await iv_service.start_interview(UUID(interview_id), UUID(user_id))
                    await db.commit()
                    await manager.send(interview_id, {"type": "interview_started", "data": result})

                elif msg_type == "answer":
                    iv_service = InterviewService(db, cache)
                    question_id = msg_data.get("question_id")
                    answer_text = msg_data.get("answer_text", "")
                    duration = msg_data.get("duration_seconds")

                    result = await iv_service.submit_answer(
                        UUID(interview_id), UUID(user_id),
                        UUID(question_id), answer_text,
                        duration_seconds=duration,
                    )
                    await db.commit()

                    # Analyze speech if duration provided
                    if duration and answer_text:
                        speech_metrics = speech_analyzer.analyze_transcript(answer_text, duration)
                        result["speech_metrics"] = speech_metrics

                    await manager.send(interview_id, {"type": "answer_result", "data": result})

                elif msg_type == "speech_chunk":
                    # Handle audio transcription
                    import base64
                    audio_b64 = msg_data.get("audio", "")
                    if audio_b64:
                        audio_bytes = base64.b64decode(audio_b64)
                        
                        # Store in sliding audio chunk cache
                        if interview_id not in audio_buffers:
                            audio_buffers[interview_id] = []
                        audio_buffers[interview_id].append(audio_bytes)
                        if len(audio_buffers[interview_id]) > 60:
                            audio_buffers[interview_id].pop(0)

                        # Single chunk transcription pass
                        transcript = await transcribe_audio(audio_bytes)
                        await manager.send(interview_id, {
                            "type": "transcript",
                            "data": {"text": transcript},
                        })

                elif msg_type == "transcript_update":
                    text = msg_data.get("text", "")
                    confidence = msg_data.get("confidence", 1.0)

                    if text:
                        # ── Debounced analysis: cancel pending task and reschedule ──
                        # This prevents LLM calls on every word during active speech.
                        # Analysis only fires after 2 seconds of silence in the transcript stream.
                        if transcript_debounce_task and not transcript_debounce_task.done():
                            transcript_debounce_task.cancel()

                        async def run_analysis(_text=text, _conf=confidence):
                            await asyncio.sleep(2.0)  # debounce: wait 2s before running LLM analysis
                            try:
                                iv_service = InterviewService(db, cache)
                                state = await iv_service.get_or_restore_interview_state(UUID(interview_id), UUID(user_id))
                                start_time_str = state.get("phase_start_time")
                                duration = 10.0
                                if start_time_str:
                                    try:
                                        start_time = datetime.fromisoformat(start_time_str)
                                        if start_time.tzinfo is None:
                                            start_time = start_time.replace(tzinfo=timezone.utc)
                                        duration = max(1.0, (datetime.now(timezone.utc) - start_time).total_seconds())
                                    except Exception:
                                        pass

                                metrics = speech_analyzer.analyze_transcript(_text, duration)
                                metrics["confidence"] = _conf

                                # Silent Skill extraction and Question Pregeneration in background
                                skills = metrics.get("skills_extracted", [])
                                resume_data = state.get("resume_data") or {"skills": [], "projects": []}
                                updated_resume = False

                                if skills:
                                    if "skills" not in resume_data or not isinstance(resume_data["skills"], list):
                                        resume_data["skills"] = []
                                    for skill in skills:
                                        existing_skills = [
                                            s.get("name").lower() if isinstance(s, dict) else s.lower()
                                            for s in resume_data["skills"]
                                        ]
                                        if skill.lower() not in existing_skills:
                                            resume_data["skills"].append({"name": skill, "proficiency": "intermediate"})
                                            updated_resume = True

                                if updated_resume:
                                    state["resume_data"] = resume_data
                                    await cache.set_interview_state(str(interview_id), state)
                                    curr_idx = state.get("question_index", 0)
                                    asyncio.create_task(iv_service.preload_next_questions_task(UUID(interview_id), UUID(user_id), curr_idx))

                                await manager.send(interview_id, {
                                    "type": "speech_analysis",
                                    "data": metrics
                                })
                            except asyncio.CancelledError:
                                pass  # Debounced away — do nothing

                        transcript_debounce_task = asyncio.create_task(run_analysis())

                elif msg_type == "proctor_event":
                    ac_service = AntiCheatService(db)
                    await ac_service.log_event(
                        interview_id=UUID(interview_id),
                        event_type=msg_data.get("event_type", "tab_switch"),
                        details=msg_data.get("details"),
                        metadata=msg_data.get("metadata"),
                        confidence=msg_data.get("confidence"),
                    )
                    await db.commit()
                    await manager.send(interview_id, {
                        "type": "proctor_ack",
                        "data": {"logged": True},
                    })

                elif msg_type == "end":
                    iv_service = InterviewService(db, cache)
                    interview = await iv_service.get_interview(UUID(interview_id), UUID(user_id))
                    interview.status = InterviewStatus.COMPLETED
                    interview.current_phase = InterviewPhase.COMPLETED
                    interview.completed_at = datetime.now(timezone.utc)
                    await db.commit()
                    await manager.send(interview_id, {
                        "type": "interview_ended",
                        "data": {"interview_id": interview_id},
                    })

                else:
                    await manager.send(interview_id, {
                        "type": "error",
                        "data": {"message": f"Unknown message type: {msg_type}"},
                    })

    except WebSocketDisconnect:
        logger.info("ws_disconnected", interview_id=interview_id)
    except Exception as e:
        import traceback
        traceback.print_exc()
        logger.error("ws_error", interview_id=interview_id, error=str(e))
        await manager.send(interview_id, {"type": "error", "data": {"message": f"Internal error: {repr(e)} - {traceback.format_exc()}"}})
    finally:
        manager.disconnect(interview_id)
