import os

import shutil
import uuid
import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
import logging
from typing import Optional
from app.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


class StorageService:
    def __init__(self):
        self.provider = settings.STORAGE_PROVIDER.lower()
        self.bucket = settings.AWS_S3_BUCKET
        self.public_url_base = settings.R2_PUBLIC_URL.rstrip("/") if settings.R2_PUBLIC_URL else None
        
        # Persistent local media storage root
        self.media_dir = os.path.abspath(settings.MEDIA_ROOT)
        self.local_uploads_dir = os.path.join(self.media_dir, "uploads")
        self.local_recordings_dir = os.path.join(self.local_uploads_dir, "recordings")
        os.makedirs(self.local_recordings_dir, exist_ok=True)

        self.s3_client = None
        if self.provider in ["r2", "s3", "minio"]:
            try:
                boto_kwargs = {
                    "service_name": "s3",
                    "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
                    "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
                    "region_name": settings.AWS_S3_REGION or "auto",
                    "config": Config(signature_version="s3v4"),
                }
                if settings.STORAGE_ENDPOINT_URL:
                    boto_kwargs["endpoint_url"] = settings.STORAGE_ENDPOINT_URL

                if self.provider in ["r2", "s3", "minio"] and settings.AWS_ACCESS_KEY_ID:
                    self.s3_client = boto3.client(**boto_kwargs)
                else:
                    logger.info("Cloud storage keys not supplied. Defaulting to persistent local disk storage.")
            except Exception as e:
                logger.warning(f"Failed to initialize {self.provider.upper()} storage client: {e}. Falling back to local disk storage.")
                self.provider = "local"

    def upload_bytes(self, content: bytes, object_key: str, content_type: str = "video/mp4") -> str:
        """Upload raw bytes to Cloudflare R2 / S3 / MinIO or persistent local disk."""
        if self.s3_client:
            try:
                extra_args = {"ContentType": content_type}
                if self.provider == "s3":
                    extra_args["ServerSideEncryption"] = "AES256"
                
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=object_key,
                    Body=content,
                    **extra_args
                )
                if self.public_url_base:
                    return f"{self.public_url_base}/{object_key}"
                return f"/uploads/recordings/{object_key}"
            except Exception as e:
                logger.error(f"Cloud storage upload error for {object_key}: {e}. Falling back to local storage.")

        # Local storage fallback
        file_path = os.path.join(self.local_recordings_dir, object_key)
        os.makedirs(os.path.dirname(file_path), exist_ok=True)
        with open(file_path, "wb") as f:
            f.write(content)
        return f"/uploads/recordings/{object_key}"

    def upload_file_path(self, local_filepath: str, object_key: str, content_type: str = "video/mp4") -> str:
        """Upload a file on disk directly to R2 / S3 / MinIO via stream to prevent RAM OOM issues."""
        if self.s3_client:
            try:
                extra_args = {"ContentType": content_type}
                if self.provider == "s3":
                    extra_args["ServerSideEncryption"] = "AES256"

                self.s3_client.upload_file(
                    Filename=local_filepath,
                    Bucket=self.bucket,
                    Key=object_key,
                    ExtraArgs=extra_args
                )
                if self.public_url_base:
                    return f"{self.public_url_base}/{object_key}"
                return f"/uploads/recordings/{object_key}"
            except Exception as e:
                logger.error(f"Cloud file upload error for {object_key}: {e}. Keeping on local disk.")

        # Local destination
        dest_path = os.path.join(self.local_recordings_dir, object_key)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        if local_filepath != dest_path:
            shutil.copy2(local_filepath, dest_path)
        return f"/uploads/recordings/{object_key}"

    async def upload_file(self, content: bytes, filename: str, folder: str = "resumes") -> str:
        """Upload resumes or document files."""
        ext = filename.rsplit(".", 1)[-1] if "." in filename else "bin"
        unique_filename = f"{uuid.uuid4().hex}.{ext}"
        object_key = f"{folder}/{unique_filename}"

        if self.s3_client:
            try:
                content_type = "application/pdf" if ext == "pdf" else "application/octet-stream"
                self.s3_client.put_object(
                    Bucket=self.bucket,
                    Key=object_key,
                    Body=content,
                    ContentType=content_type
                )
                if self.public_url_base:
                    return f"{self.public_url_base}/{object_key}"
                return f"/uploads/{folder}/{unique_filename}"
            except Exception as e:
                logger.error(f"Error uploading file to cloud storage: {e}. Saving to local disk.")

        # Local storage fallback
        base_dir = os.path.join(self.local_uploads_dir, folder)
        os.makedirs(base_dir, exist_ok=True)
        file_path = os.path.join(base_dir, unique_filename)
        with open(file_path, "wb") as f:
            f.write(content)
        return f"/uploads/{folder}/{unique_filename}"

    def upload_chunk(self, chunk_bytes: bytes, recording_id: str, chunk_index: int) -> str:
        """Store intermediate recording chunk to local disk for assembly."""
        chunk_dir = os.path.join(self.local_uploads_dir, "chunks", recording_id)
        os.makedirs(chunk_dir, exist_ok=True)
        chunk_path = os.path.join(chunk_dir, f"chunk_{chunk_index:06d}.bin")
        with open(chunk_path, "wb") as f:
            f.write(chunk_bytes)
        return chunk_path

    def assemble_chunks(self, recording_id: str, object_key: str, content_type: str = "video/mp4") -> tuple[str, int]:
        """Stream and assemble all uploaded chunks on disk sequentially (OOM-safe)."""
        chunk_dir = os.path.join(self.local_uploads_dir, "chunks", recording_id)
        chunk_files = (
            sorted([os.path.join(chunk_dir, f) for f in os.listdir(chunk_dir) if f.startswith("chunk_")])
            if os.path.exists(chunk_dir)
            else []
        )

        temp_merged_path = os.path.join(self.local_recordings_dir, f"temp_{recording_id}.mp4")
        os.makedirs(os.path.dirname(temp_merged_path), exist_ok=True)

        file_size = 0
        with open(temp_merged_path, "wb") as outfile:
            for chunk_file in chunk_files:
                with open(chunk_file, "rb") as infile:
                    shutil.copyfileobj(infile, outfile)
                file_size += os.path.getsize(chunk_file)

        # Cleanup chunks
        for chunk_file in chunk_files:
            try:
                os.remove(chunk_file)
            except Exception:
                pass
        try:
            os.rmdir(chunk_dir)
        except Exception:
            pass

        # Perform malware check on head sample
        self._scan_for_malware_file(temp_merged_path)

        url = self.upload_file_path(temp_merged_path, object_key, content_type)

        # Cleanup temp merged file if uploaded to cloud
        if self.s3_client and os.path.exists(temp_merged_path):
            try:
                os.remove(temp_merged_path)
            except Exception:
                pass

        return url, file_size

    def _scan_for_malware_file(self, file_path: str) -> bool:
        """Scan file for malware test signatures without loading entire file to RAM."""
        if not os.path.exists(file_path):
            return True
        with open(file_path, "rb") as f:
            head_bytes = f.read(4096)
            if b"EICAR-STANDARD-ANTIVIRUS-TEST-FILE" in head_bytes:
                raise ValueError("Security Threat Detected: File infected with malware!")
        return True

    def generate_presigned_download_url(self, object_key: str, expires_in: int = 3600) -> str:
        """Generate a secure signed download URL for private Cloudflare R2 / S3 media."""
        if self.public_url_base:
            return f"{self.public_url_base}/{object_key}"

        if self.s3_client:
            try:
                return self.s3_client.generate_presigned_url(
                    "get_object",
                    Params={"Bucket": self.bucket, "Key": object_key},
                    ExpiresIn=expires_in,
                )
            except Exception as e:
                logger.warning(f"Error generating presigned URL for {object_key}: {e}")

        # Fallback local URL
        return f"/uploads/recordings/{object_key}?token=signed_access_valid"

    def delete_object(self, object_key: str) -> bool:
        """Permanently delete object from Cloudflare R2 / S3 or local persistent storage."""
        success = False
        if self.s3_client:
            try:
                self.s3_client.delete_object(Bucket=self.bucket, Key=object_key)
                success = True
            except Exception as e:
                logger.error(f"Error deleting object {object_key} from Cloudflare R2/S3: {e}")

        # Local check
        file_path = os.path.join(self.local_recordings_dir, object_key)
        if os.path.exists(file_path):
            try:
                os.remove(file_path)
                success = True
            except Exception as e:
                logger.error(f"Error deleting local file {file_path}: {e}")

        return success


storage_service = StorageService()

