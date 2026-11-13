"""Store uploaded and generated files under the data dir; never use the client file name as path."""

from __future__ import annotations

import hashlib
from datetime import datetime
from pathlib import Path

from fastapi import UploadFile
from sqlalchemy.orm import Session

from shoponline.config import Settings
from shoponline.db.models import GeneratedFile, ImportBatch

MAX_UPLOAD_BYTES = 20 * 1024 * 1024
ALLOWED_SUFFIXES = (".xlsx",)


class UploadRejected(ValueError):
    pass


async def save_upload(
    settings: Settings, upload: UploadFile, *, kind: str, platform: str | None, actor: str
) -> ImportBatch:
    name = Path(upload.filename or "").name
    if not name.lower().endswith(ALLOWED_SUFFIXES):
        raise UploadRejected("Chỉ nhận file .xlsx")
    data = await upload.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        raise UploadRejected("File lớn hơn 20 MB")
    return store_file(settings, data, name, kind=kind, platform=platform, actor=actor)


def store_file(
    settings: Settings, data: bytes, name: str, *, kind: str, platform: str | None, actor: str
) -> ImportBatch:
    """Store the file by content hash under the upload dir; the caller adds the record."""
    if not data:
        raise UploadRejected("File rỗng")
    digest = hashlib.sha256(data).hexdigest()
    settings.upload_dir.mkdir(parents=True, exist_ok=True)
    stored = settings.upload_dir / f"{digest}.xlsx"
    if stored.exists():
        stored.touch()  # same content uploaded again: restart its retention period
    else:
        stored.write_bytes(data)
    return ImportBatch(
        kind=kind,
        platform=platform,
        file_name=name[:300],
        sha256=digest,
        stored_path=str(stored),
        imported_by=actor,
    )


def save_generated(
    session: Session, settings: Settings, workbook, file_name: str, kind: str, actor: str
) -> Path:
    settings.export_dir.mkdir(parents=True, exist_ok=True)
    path = settings.export_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{kind}.xlsx"
    workbook.save(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    session.add(
        GeneratedFile(
            kind=kind, file_name=file_name, stored_path=str(path), sha256=digest, created_by=actor
        )
    )
    return path
