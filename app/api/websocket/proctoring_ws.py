import json
from uuid import UUID
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.database import async_session
from app.utils.security import decode_token
from app.services.cv_service import CVAnalysisService
from app.services.anti_cheat_service import AntiCheatService
from app.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter()

# No global session state to avoid memory leaks/race conditions. CV services are local to handlers.

@router.websocket("/ws/proctor/{interview_id}")
async def proctoring_websocket(websocket: WebSocket, interview_id: str):
    """
    Separate WebSocket for high-frequency proctoring data.
    Receives video frames and returns analysis results.
    Keeps the main interview WS clean for Q&A flow.
    """
    # Validate UUID format
    try:
        UUID(interview_id)
    except ValueError:
        await websocket.close(code=4002, reason="Invalid interview ID")
        return

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

    await websocket.accept()

    cv_service = CVAnalysisService()

    logger.info("proctor_ws_connected", interview_id=interview_id)
    frame_count = 0

    try:
        while True:
            raw = await websocket.receive_text()
            try:
                message = json.loads(raw)
            except json.JSONDecodeError:
                continue

            msg_type = message.get("type", "")

            if msg_type == "video_frame":
                frame_b64 = message.get("data", {}).get("frame", "")
                if not frame_b64:
                    continue

                analysis = cv_service.analyze_frame_base64(frame_b64)
                frame_count += 1

                # Only send back every 5th frame to reduce bandwidth
                if frame_count % 5 == 0:
                    await websocket.send_json({
                        "type": "frame_analysis",
                        "data": {
                            "face_count": analysis.face_count,
                            "has_face": analysis.has_face,
                            "eye_contact": analysis.eye_contact_score,
                            "confidence": analysis.confidence_score,
                            "head_yaw": analysis.head_pose_yaw,
                            "emotions": analysis.emotion_scores,
                        },
                    })

                # Log proctor events only when suspicious activity detected
                has_violation = (
                    analysis.face_count > 1
                    or not analysis.has_face
                    or analysis.eye_contact_score < 0.2
                )

                # Throttle no_face and gaze_deviation to every 10th frame to avoid DB flood
                if has_violation and (
                    analysis.face_count > 1  # always log multiple faces immediately
                    or frame_count % 10 == 0  # throttle other violations
                ):
                    async with async_session() as db:
                        ac_service = AntiCheatService(db)

                        if analysis.face_count > 1:
                            await ac_service.log_event(
                                UUID(interview_id),
                                "multiple_faces",
                                f"Detected {analysis.face_count} faces",
                                {"face_count": analysis.face_count},
                                confidence=0.8,
                            )
                        elif not analysis.has_face:
                            await ac_service.log_event(
                                UUID(interview_id),
                                "no_face",
                                "No face detected in frame",
                                confidence=0.7,
                            )
                        elif analysis.eye_contact_score < 0.2:
                            await ac_service.log_event(
                                UUID(interview_id),
                                "gaze_deviation",
                                f"Low eye contact: {analysis.eye_contact_score:.2f}",
                                {
                                    "eye_contact": analysis.eye_contact_score,
                                    "head_yaw": analysis.head_pose_yaw,
                                },
                                confidence=analysis.eye_contact_score,
                            )
                        await db.commit()

            elif msg_type == "get_summary":
                summary = cv_service.get_session_summary()
                await websocket.send_json({
                    "type": "session_summary",
                    "data": summary,
                })

                # Store summary on interview record
                async with async_session() as db:
                    from sqlalchemy import select, update
                    from app.models.interview import Interview
                    await db.execute(
                        update(Interview)
                        .where(Interview.id == UUID(interview_id))
                        .values(emotion_metrics=summary)
                    )
                    await db.commit()

    except WebSocketDisconnect:
        logger.info("proctor_ws_disconnected", interview_id=interview_id, frames=frame_count)
    except Exception as e:
        logger.error("proctor_ws_error", interview_id=interview_id, error=str(e))
    finally:
        # Store final session summary before cleanup using the local service variable
        try:
            summary = cv_service.get_session_summary()
            async with async_session() as db:
                from sqlalchemy import update
                from app.models.interview import Interview
                await db.execute(
                    update(Interview)
                    .where(Interview.id == UUID(interview_id))
                    .values(
                        emotion_metrics=summary,
                        confidence_score=summary.get("avg_confidence", 0) * 10,
                    )
                )
                await db.commit()
        except Exception:
            pass
