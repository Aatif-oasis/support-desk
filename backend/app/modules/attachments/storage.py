"""
StorageBackend is the seam between "where files physically live" and
everything else. LocalDiskStorage is what runs today; a future
S3Storage/GCSStorage implementing the same two methods drops in with zero
changes to the attachments service — that's the whole point of having this
abstraction instead of calling `open()` directly from the service layer.
"""
import uuid
from pathlib import Path

from app.core.config import settings


class LocalDiskStorage:
    def __init__(self, base_dir: str = settings.UPLOAD_DIR):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    async def save(self, organization_id: uuid.UUID, filename: str, content: bytes) -> str:
        """
        Returns a storage_path — an opaque identifier the DB stores and
        later passes back to `read`/`delete`. Callers must never assume
        this is a filesystem path they can open directly (an S3 backend's
        storage_path would be a bucket key, not something `open()`-able).
        """
        org_dir = self.base_dir / str(organization_id)
        org_dir.mkdir(parents=True, exist_ok=True)

        safe_name = Path(filename).name  # strip any directory traversal attempt
        unique_name = f"{uuid.uuid4().hex}_{safe_name}"
        full_path = org_dir / unique_name
        full_path.write_bytes(content)

        return f"{organization_id}/{unique_name}"

    async def read(self, storage_path: str) -> bytes:
        full_path = self.base_dir / storage_path
        return full_path.read_bytes()

    async def delete(self, storage_path: str) -> None:
        full_path = self.base_dir / storage_path
        full_path.unlink(missing_ok=True)


storage_backend = LocalDiskStorage()
