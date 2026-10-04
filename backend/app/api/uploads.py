"""Reading uploaded files without trusting their declared size."""

from __future__ import annotations

from fastapi import HTTPException, UploadFile

_CHUNK = 1024 * 1024


async def read_upload(file: UploadFile, limit: int) -> bytes:
    """Read an upload in chunks, stopping as soon as it exceeds ``limit`` bytes."""
    parts: list[bytes] = []
    size = 0
    while chunk := await file.read(_CHUNK):
        size += len(chunk)
        if size > limit:
            raise HTTPException(status_code=413, detail=f"{file.filename or 'File'} is larger than {limit // (1024 * 1024)} MB")
        parts.append(chunk)
    if not size:
        raise HTTPException(status_code=422, detail=f"{file.filename or 'The file'} is empty")
    return b"".join(parts)
