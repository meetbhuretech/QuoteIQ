"""Object storage. Local files in development, S3-compatible storage in production."""

from __future__ import annotations

from pathlib import Path
from uuid import uuid4

from app.core.config import get_settings
from app.core.errors import AppError


class Storage:
    def save(self, organization_id: str, filename: str, data: bytes) -> str:
        raise NotImplementedError

    def read(self, key: str) -> bytes:
        raise NotImplementedError

    def absolute(self, key: str) -> Path | None:
        return None


class LocalStorage(Storage):
    def __init__(self, root: str):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def save(self, organization_id: str, filename: str, data: bytes) -> str:
        suffix = Path(filename).suffix.lower()[:10]
        key = f"{organization_id}/{uuid4().hex}{suffix}"
        path = self._path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def read(self, key: str) -> bytes:
        return self._path(key).read_bytes()

    def absolute(self, key: str) -> Path:
        return self._path(key)

    def _path(self, key: str) -> Path:
        path = (self.root / key).resolve()
        if path != self.root and self.root not in path.parents:
            raise AppError(400, "Invalid storage key")
        return path


class S3Storage(Storage):
    def __init__(self):
        settings = get_settings()
        if not settings.s3_bucket:
            raise AppError(500, "S3_BUCKET is required when STORAGE_BACKEND=s3")
        import boto3

        self.bucket = settings.s3_bucket
        self.client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.s3_access_key_id,
            aws_secret_access_key=settings.s3_secret_access_key,
            region_name=settings.s3_region,
        )

    def save(self, organization_id: str, filename: str, data: bytes) -> str:
        suffix = Path(filename).suffix.lower()[:10]
        key = f"{organization_id}/{uuid4().hex}{suffix}"
        self.client.put_object(Bucket=self.bucket, Key=key, Body=data)
        return key

    def read(self, key: str) -> bytes:
        response = self.client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()


def get_storage() -> Storage:
    settings = get_settings()
    if settings.storage_backend == "s3":
        return S3Storage()
    return LocalStorage(settings.storage_dir)
