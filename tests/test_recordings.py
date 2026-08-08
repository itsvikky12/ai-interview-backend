import pytest
import base64
from datetime import datetime, timezone, timedelta
from app.models.recording import InterviewRecording, RecordingStatus
from app.models.user import User, UserRole
from app.models.interview import Interview, InterviewStatus
from app.services.recording_service import recording_service
from app.tasks.cleanup_task import run_daily_retention_cleanup


@pytest.mark.asyncio
async def test_recording_lifecycle(db_session):
    # 1. Setup Student & Interview
    student = User(
        email="test_record_student@example.com",
        hashed_password="hash",
        full_name="Recording Student",
        role=UserRole.STUDENT
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)

    interview = Interview(
        user_id=student.id,
        target_role="Senior AI Engineer",
        status=InterviewStatus.IN_PROGRESS
    )
    db_session.add(interview)
    await db_session.commit()
    await db_session.refresh(interview)

    # 2. Start Recording Session
    recording = await recording_service.create_recording_session(
        db_session,
        interview_id=interview.id,
        student_id=student.id,
        resolution="1080p",
        format="mp4"
    )
    assert recording is not None
    assert recording.upload_status == RecordingStatus.RECORDING
    assert recording.resolution == "1080p"

    # 3. Save Upload Chunks
    dummy_bytes = b"HEADER_DUMMY_WEBM_VIDEO_DATA_CHUNK_0"
    chunk_path = await recording_service.save_chunk(recording.id, dummy_bytes, 0)
    assert chunk_path is not None

    # 4. Complete Recording Upload & Assembly
    completed = await recording_service.complete_recording_upload(
        db_session,
        recording_id=recording.id,
        duration=120.0,
        resolution="1080p"
    )
    assert completed.upload_status == RecordingStatus.READY
    assert completed.file_size > 0
    assert completed.duration == 120.0
    assert completed.recording_url is not None

    # 5. Extend Retention Expiry (Admin)
    extended = await recording_service.extend_expiry(
        db_session,
        recording_id=completed.id,
        actor_id="admin_123",
        additional_days=7
    )
    assert extended.is_extended is True

    # 6. Delete Recording Media
    deleted_success = await recording_service.delete_recording(
        db_session,
        recording_id=completed.id,
        actor_id=student.id,
        actor_role="student",
        reason="Test cleanup"
    )
    assert deleted_success is True
    assert completed.upload_status == RecordingStatus.DELETED
    assert completed.recording_url is None


@pytest.mark.asyncio
async def test_retention_cleanup_task(db_session):
    # Setup user & interview
    student = User(
        email="cleanup_student@example.com",
        hashed_password="hash",
        full_name="Cleanup Student",
        role=UserRole.STUDENT
    )
    db_session.add(student)
    await db_session.commit()
    await db_session.refresh(student)

    interview = Interview(
        user_id=student.id,
        target_role="Fullstack Developer",
        status=InterviewStatus.COMPLETED
    )
    db_session.add(interview)
    await db_session.commit()
    await db_session.refresh(interview)

    # Create an expired recording (expires_at in past)
    past_expiry = datetime.now(timezone.utc) - timedelta(days=1)
    expired_rec = InterviewRecording(
        interview_id=interview.id,
        student_id=student.id,
        upload_status=RecordingStatus.READY,
        expires_at=past_expiry,
        recording_url="/uploads/recordings/test.mp4"
    )
    db_session.add(expired_rec)
    await db_session.commit()

    # Execute Cleanup Job
    results = await run_daily_retention_cleanup(db_session)
    assert results["purged_count"] >= 1

    await db_session.refresh(expired_rec)
    assert expired_rec.upload_status == RecordingStatus.DELETED
    assert expired_rec.recording_url is None
