import base64
import csv
import io
from datetime import datetime, timezone, timedelta
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException, status, Query, Response as FastAPIResponse
from fastapi.responses import StreamingResponse, Response, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func, or_, and_
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.dependencies import get_current_user, get_admin_user
from app.models.user import User, UserRole
from app.models.interview import Interview
from app.models.recording import InterviewRecording, RecordingStatus, Notification
from app.schemas.recording import (
    RecordingCreate,
    RecordingChunkUpload,
    RecordingCompleteUpload,
    RecordingExtendExpiry,
    RecordingResponse,
    AdminRecordingStats,
    NotificationResponse,
)
from app.services.recording_service import recording_service
from app.services.storage_service import storage_service
from app.services.notification_service import notification_service
from app.tasks.cleanup_task import run_daily_retention_cleanup

router = APIRouter(prefix="/recordings", tags=["Recordings"])


def _format_recording_response(rec: InterviewRecording) -> dict:
    now = datetime.now(timezone.utc)
    exp = rec.expires_at
    if exp and exp.tzinfo is None:
        exp = exp.replace(tzinfo=timezone.utc)
    remaining_days = max(0.0, round((exp - now).total_seconds() / 86400.0, 2)) if exp else 0.0

    target_role = rec.interview.target_role if rec.interview else "Software Engineer"
    score = rec.interview.overall_score if rec.interview else None
    student_name = rec.student.full_name if rec.student else "Student"

    return {
        "id": rec.id,
        "interview_id": rec.interview_id,
        "student_id": rec.student_id,
        "recording_url": rec.recording_url,
        "thumbnail_url": rec.thumbnail_url,
        "transcript_url": rec.transcript_url,
        "pdf_report_url": rec.pdf_report_url,
        "duration": rec.duration,
        "resolution": rec.resolution,
        "format": rec.format,
        "file_size": rec.file_size,
        "upload_status": rec.upload_status.value if hasattr(rec.upload_status, "value") else str(rec.upload_status),
        "storage_provider": rec.storage_provider,
        "download_count": rec.download_count,
        "view_count": rec.view_count,
        "last_viewed_at": rec.last_viewed_at,
        "ai_markers": rec.ai_markers,
        "is_extended": rec.is_extended,
        "created_at": rec.created_at,
        "expires_at": rec.expires_at,
        "deleted_at": rec.deleted_at,
        "interview_target_role": target_role,
        "student_name": student_name,
        "company_name": "AI Platform",
        "overall_score": score,
        "remaining_days": remaining_days,
    }


@router.post("/start", status_code=status.HTTP_201_CREATED)
async def start_recording(
    payload: RecordingCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Start an interview recording session."""
    try:
        rec = await recording_service.create_recording_session(
            db,
            interview_id=payload.interview_id,
            student_id=current_user.id,
            resolution=payload.resolution,
            format=payload.format,
        )
        return _format_recording_response(rec)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{recording_id}/stop")
async def stop_recording(
    recording_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stop recording session."""
    rec = await recording_service.get_recording_by_id(db, recording_id)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording session not found")
    if current_user.role != UserRole.ADMIN and rec.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    rec.upload_status = RecordingStatus.UPLOADING
    await db.commit()
    return {"message": "Recording stopped successfully. Proceed to upload completion.", "recording_id": rec.id}


@router.post("/{recording_id}/upload-chunk")
async def upload_recording_chunk(
    recording_id: str,
    payload: RecordingChunkUpload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Upload base64 encoded video chunk for resumable recording."""
    rec = await recording_service.get_recording_by_id(db, recording_id)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    if current_user.role != UserRole.ADMIN and rec.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    try:
        b64_data = payload.chunk_data_base64
        if "," in b64_data:
            b64_data = b64_data.split(",", 1)[1]
        chunk_bytes = base64.b64decode(b64_data)
        chunk_path = await recording_service.save_chunk(recording_id, chunk_bytes, payload.chunk_index)
        return {"status": "chunk_received", "chunk_index": payload.chunk_index, "path": chunk_path}
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Failed to process chunk: {e}")


@router.post("/{recording_id}/upload-complete")
async def complete_recording_upload(
    recording_id: str,
    payload: RecordingCompleteUpload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Finalize chunk assembly and trigger AI marker and transcript generation."""
    rec = await recording_service.get_recording_by_id(db, recording_id)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")
    if current_user.role != UserRole.ADMIN and rec.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    try:
        final_rec = await recording_service.complete_recording_upload(
            db, recording_id, duration=payload.duration, resolution=payload.resolution
        )
        return _format_recording_response(final_rec)
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.get("/student")
async def get_student_recordings(
    search: Optional[str] = Query(None),
    sort_by: str = Query("date", description="date or score"),
    category: str = Query("all", description="all, recent, mock, company"),
    page: int = Query(1, ge=1),
    limit: int = Query(10, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List recordings for current student with filters, search, and sorting."""
    stmt = (
        select(InterviewRecording)
        .options(selectinload(InterviewRecording.interview), selectinload(InterviewRecording.student))
        .where(InterviewRecording.student_id == current_user.id)
    )

    if search:
        stmt = stmt.join(InterviewRecording.interview).where(
            or_(
                Interview.target_role.ilike(f"%{search}%"),
                InterviewRecording.id.ilike(f"%{search}%"),
            )
        )

    if category == "recent":
        seven_days_ago = datetime.now(timezone.utc) - timedelta(days=3)
        stmt = stmt.where(InterviewRecording.created_at >= seven_days_ago)

    if sort_by == "date":
        stmt = stmt.order_by(InterviewRecording.created_at.desc())

    offset = (page - 1) * limit
    stmt = stmt.offset(offset).limit(limit)

    res = await db.execute(stmt)
    recordings = res.scalars().all()

    items = [_format_recording_response(r) for r in recordings]
    if sort_by == "score":
        items.sort(key=lambda x: (x.get("overall_score") or 0.0), reverse=True)

    return {
        "items": items,
        "page": page,
        "limit": limit,
        "total": len(items)
    }


@router.get("/admin")
async def get_admin_recordings(
    search: Optional[str] = Query(None),
    status_filter: Optional[str] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """List all platform recordings for Admin."""
    stmt = (
        select(InterviewRecording)
        .options(selectinload(InterviewRecording.interview), selectinload(InterviewRecording.student))
        .order_by(InterviewRecording.created_at.desc())
    )

    if status_filter:
        stmt = stmt.where(InterviewRecording.upload_status == status_filter)

    offset = (page - 1) * limit
    stmt = stmt.offset(offset).limit(limit)

    res = await db.execute(stmt)
    recordings = res.scalars().all()
    items = [_format_recording_response(r) for r in recordings]

    if search:
        s = search.lower()
        items = [
            i for i in items
            if s in i["id"].lower()
            or s in i["student_name"].lower()
            or s in i["interview_target_role"].lower()
        ]

    return {"items": items, "page": page, "limit": limit, "total": len(items)}


@router.get("/admin/stats", response_model=AdminRecordingStats)
async def get_admin_recording_stats(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Get storage and recording retention analytics for Admin Dashboard."""
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    expiring_end = now + timedelta(hours=24)

    total_res = await db.execute(select(func.count(InterviewRecording.id)))
    total_recordings = total_res.scalar() or 0

    storage_res = await db.execute(
        select(func.sum(InterviewRecording.file_size)).where(InterviewRecording.upload_status == RecordingStatus.READY)
    )
    total_storage_bytes = storage_res.scalar() or 0

    active_res = await db.execute(
        select(func.count(InterviewRecording.id)).where(InterviewRecording.upload_status == RecordingStatus.READY)
    )
    active_recordings = active_res.scalar() or 0

    expiring_res = await db.execute(
        select(func.count(InterviewRecording.id)).where(
            InterviewRecording.upload_status == RecordingStatus.READY,
            InterviewRecording.expires_at <= expiring_end,
            InterviewRecording.expires_at > now
        )
    )
    expiring_today = expiring_res.scalar() or 0

    deleted_res = await db.execute(
        select(func.count(InterviewRecording.id)).where(
            InterviewRecording.upload_status == RecordingStatus.DELETED,
            InterviewRecording.deleted_at >= today_start
        )
    )
    deleted_today = deleted_res.scalar() or 0

    daily_uploads_res = await db.execute(
        select(func.count(InterviewRecording.id)).where(InterviewRecording.created_at >= today_start)
    )
    daily_uploads_count = daily_uploads_res.scalar() or 0

    return AdminRecordingStats(
        total_recordings=total_recordings,
        total_storage_bytes=total_storage_bytes,
        active_recordings=active_recordings,
        expiring_today=expiring_today,
        deleted_today=deleted_today,
        daily_uploads_count=daily_uploads_count
    )


@router.get("/{recording_id}")
async def get_recording_detail(
    recording_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get single recording detail & increment view count."""
    rec = await recording_service.get_recording_by_id(db, recording_id)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")

    if current_user.role != UserRole.ADMIN and rec.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Increment view count
    rec.view_count += 1
    rec.last_viewed_at = datetime.now(timezone.utc)
    await db.commit()

    return _format_recording_response(rec)


@router.get("/{recording_id}/stream")
async def stream_recording_media(
    recording_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Stream recording media with presigned URL or local binary fallback."""
    rec = await recording_service.get_recording_by_id(db, recording_id)
    if not rec or rec.upload_status in [RecordingStatus.DELETED, RecordingStatus.EXPIRED]:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording media unavailable or deleted")

    if current_user.role != UserRole.ADMIN and rec.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    object_key = f"interviews/{rec.interview_id}/{rec.id}.mp4"
    signed_url = storage_service.generate_presigned_download_url(object_key, expires_in=3600)

    return {"stream_url": signed_url, "expires_in": 3600, "mime_type": "video/mp4"}


@router.get("/{recording_id}/download/{file_type}")
async def download_recording_asset(
    recording_id: str,
    file_type: str,  # mp4, pdf, transcript, srt, vtt
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Download recording assets (MP4 video, PDF report, Transcript, SRT/VTT subtitles)."""
    rec = await recording_service.get_recording_by_id(db, recording_id)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")

    if current_user.role != UserRole.ADMIN and rec.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    if rec.upload_status == RecordingStatus.DELETED and file_type == "mp4":
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Recording video file has expired and been deleted")

    # Audit & count tracking
    rec.download_count += 1
    await db.commit()
    await recording_service.log_audit(
        db, rec.id, current_user.id, current_user.role.value, "file_download", {"file_type": file_type}
    )

    filename_prefix = f"interview_recording_{rec.interview_id[:8]}"

    if file_type == "mp4":
        object_key = f"interviews/{rec.interview_id}/{rec.id}.mp4"
        signed_url = storage_service.generate_presigned_download_url(object_key, expires_in=1800)
        return {"download_url": signed_url, "filename": f"{filename_prefix}.mp4"}

    elif file_type == "vtt":
        vtt_content = await recording_service.generate_vtt_subtitle(db, rec)
        return Response(
            content=vtt_content,
            media_type="text/vtt",
            headers={"Content-Disposition": f'attachment; filename="{filename_prefix}.vtt"'}
        )

    elif file_type == "srt":
        srt_content = await recording_service.generate_srt_subtitle(db, rec)
        return Response(
            content=srt_content,
            media_type="application/x-subrip",
            headers={"Content-Disposition": f'attachment; filename="{filename_prefix}.srt"'}
        )

    elif file_type == "transcript":
        vtt_content = await recording_service.generate_vtt_subtitle(db, rec)
        # Strip timestamps for clean text transcript
        clean_text = "\n".join([line for line in vtt_content.splitlines() if not ("-->" in line or line.isdigit() or line == "WEBVTT")])
        return Response(
            content=clean_text.strip(),
            media_type="text/plain",
            headers={"Content-Disposition": f'attachment; filename="{filename_prefix}_transcript.txt"'}
        )

    elif file_type == "pdf":
        return {
            "download_url": f"/api/v1/reports/{rec.interview_id}/pdf",
            "filename": f"{filename_prefix}_report.pdf"
        }

    else:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported download file type: {file_type}")


@router.delete("/{recording_id}")
async def delete_recording(
    recording_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Delete recording media permanently."""
    rec = await recording_service.get_recording_by_id(db, recording_id)
    if not rec:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Recording not found")

    if current_user.role != UserRole.ADMIN and rec.student_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    success = await recording_service.delete_recording(
        db,
        recording_id=recording_id,
        actor_id=current_user.id,
        actor_role=current_user.role.value,
        reason="Manual user deletion request"
    )

    return {"message": "Recording media deleted successfully", "success": success}


@router.post("/{recording_id}/extend-expiry")
async def extend_recording_expiry(
    recording_id: str,
    payload: RecordingExtendExpiry,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Extend recording retention window (Admin command)."""
    try:
        updated_rec = await recording_service.extend_expiry(
            db, recording_id, actor_id=admin.id, additional_days=payload.additional_days
        )
        return _format_recording_response(updated_rec)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/admin/bulk-delete")
async def bulk_delete_recordings(
    recording_ids: List[str],
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Bulk delete list of recordings (Admin command)."""
    deleted = 0
    for rid in recording_ids:
        try:
            res = await recording_service.delete_recording(
                db, rid, actor_id=admin.id, actor_role="admin", reason="Admin bulk deletion"
            )
            if res:
                deleted += 1
        except Exception as e:
            logger.error(f"Failed to delete recording {rid} in bulk operation: {e}")

    return {"message": f"Successfully deleted {deleted} of {len(recording_ids)} recordings", "deleted_count": deleted}


@router.get("/admin/export")
async def export_recording_metadata(
    format_type: str = Query("csv", description="csv or json"),
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Export recording metadata as CSV or JSON for compliance audit."""
    res = await db.execute(
        select(InterviewRecording).options(
            selectinload(InterviewRecording.interview), selectinload(InterviewRecording.student)
        )
    )
    recordings = res.scalars().all()
    formatted = [_format_recording_response(r) for r in recordings]

    if format_type == "json":
        return JSONResponse(content=formatted)

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "id", "interview_id", "student_name", "interview_target_role",
            "duration", "resolution", "file_size", "upload_status",
            "download_count", "view_count", "created_at", "expires_at"
        ]
    )
    writer.writeheader()
    for row in formatted:
        writer.writerow({
            "id": row["id"],
            "interview_id": row["interview_id"],
            "student_name": row["student_name"],
            "interview_target_role": row["interview_target_role"],
            "duration": row["duration"],
            "resolution": row["resolution"],
            "file_size": row["file_size"],
            "upload_status": row["upload_status"],
            "download_count": row["download_count"],
            "view_count": row["view_count"],
            "created_at": row["created_at"].isoformat() if row["created_at"] else "",
            "expires_at": row["expires_at"].isoformat() if row["expires_at"] else "",
        })

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="recording_metadata_export.csv"'}
    )


@router.post("/cleanup-trigger")
async def trigger_cleanup(
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    """Trigger 7-day retention cleanup job manually."""
    res = await run_daily_retention_cleanup(db)
    return {"message": "Retention cleanup executed successfully", "results": res}


@router.get("/notifications", response_model=List[NotificationResponse])
async def get_user_notifications(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get notifications for current user."""
    return await notification_service.get_user_notifications(db, current_user.id)


@router.patch("/notifications/{notification_id}/read")
async def mark_notification_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mark notification as read."""
    success = await notification_service.mark_as_read(db, notification_id, current_user.id)
    return {"success": success}
