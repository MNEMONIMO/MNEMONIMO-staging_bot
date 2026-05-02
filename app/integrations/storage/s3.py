import uuid
import boto3
from botocore.exceptions import ClientError
from loguru import logger
from app.core.config import settings


class StorageService:
    """S3-compatible file storage."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            self._client = boto3.client(
                "s3",
                endpoint_url=settings.s3_endpoint_url,
                aws_access_key_id=settings.s3_access_key,
                aws_secret_access_key=settings.s3_secret_key,
                region_name=settings.s3_region,
            )
        return self._client

    def upload_bytes(
        self,
        data: bytes,
        prefix: str = "uploads",
        extension: str = "jpg",
        content_type: str = "image/jpeg",
    ) -> str:
        """Upload bytes to S3. Returns the storage path."""
        key = f"{prefix}/{uuid.uuid4().hex}.{extension}"
        try:
            self.client.put_object(
                Bucket=settings.s3_bucket_name,
                Key=key,
                Body=data,
                ContentType=content_type,
            )
            logger.info(f"Uploaded file: {key}")
            return key
        except ClientError as e:
            logger.error(f"S3 upload failed: {e}")
            raise

    def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Generate a presigned URL for private access."""
        try:
            url = self.client.generate_presigned_url(
                "get_object",
                Params={"Bucket": settings.s3_bucket_name, "Key": key},
                ExpiresIn=expires_in,
            )
            return url
        except ClientError as e:
            logger.error(f"Failed to generate presigned URL: {e}")
            raise

    def download_bytes(self, key: str) -> bytes:
        """Download file bytes from S3."""
        try:
            response = self.client.get_object(
                Bucket=settings.s3_bucket_name, Key=key
            )
            return response["Body"].read()
        except ClientError as e:
            logger.error(f"S3 download failed: {e}")
            raise

    def delete(self, key: str) -> None:
        try:
            self.client.delete_object(Bucket=settings.s3_bucket_name, Key=key)
        except ClientError as e:
            logger.error(f"S3 delete failed: {e}")


storage_service = StorageService()
