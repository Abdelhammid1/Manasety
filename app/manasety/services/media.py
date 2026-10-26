"""Uploads: type is checked from the file content (not the extension), images become WebP,
alt text is mandatory, size is capped."""
from __future__ import annotations

import io
import secrets
from pathlib import Path

from flask import current_app
from PIL import Image, UnidentifiedImageError
from werkzeug.datastructures import FileStorage

from ..models import Media

MAX_IMAGE_SIDE = 2400
PDF_MAGIC = b"%PDF-"
MP4_MARKERS = (b"ftypmp4", b"ftypisom", b"ftypM4V", b"ftypavc1")


# Files under MEDIA_DIR/private are never served by /media: display files (served only through their
# public path, so "direct link off" really turns them off).
PRIVATE_DIR = "private"


class UploadError(ValueError):
    pass


def media_dir() -> Path:
    path = Path(current_app.config["MEDIA_DIR"])
    path.mkdir(parents=True, exist_ok=True)
    return path


def sniff(data: bytes) -> str:
    if data.startswith(PDF_MAGIC):
        return "pdf"
    if any(m in data[:32] for m in MP4_MARKERS):
        return "video"
    try:
        with Image.open(io.BytesIO(data)) as img:
            img.verify()
        return "image"
    except (UnidentifiedImageError, OSError, SyntaxError):
        return "unknown"


def save_upload(file: FileStorage, alt: str, alt_en: str = "") -> Media:
    if not file or not file.filename:
        raise UploadError("اختر ملفًا.")
    data = file.read()
    kind = sniff(data)
    if kind == "unknown":
        raise UploadError("نوع الملف غير مسموح. المسموح: صور، PDF، فيديو MP4.")
    if kind == "image" and not alt.strip():
        raise UploadError("النص البديل (alt) إلزامي لكل صورة.")
    if kind == "image" and len(data) > current_app.config["MAX_IMAGE_MB"] * 1024 * 1024:
        raise UploadError(f"حجم الصورة أكبر من {current_app.config['MAX_IMAGE_MB']} ميجا.")

    token = secrets.token_hex(8)
    width = height = None
    if kind == "image":
        data, width, height = to_webp(data)
        filename, mime = f"{token}.webp", "image/webp"
    elif kind == "pdf":
        filename, mime = f"{token}.pdf", "application/pdf"
    else:
        filename, mime = f"{token}.mp4", "video/mp4"

    (media_dir() / filename).write_bytes(data)
    return Media(filename=filename, original_name=Path(file.filename).name[:255], mime=mime, kind=kind,
                 size=len(data), width=width, height=height, alt=alt.strip(), alt_en=alt_en.strip())


def to_webp(data: bytes) -> tuple[bytes, int, int]:
    with Image.open(io.BytesIO(data)) as img:
        img.load()
        if img.mode not in ("RGB", "RGBA"):
            img = img.convert("RGBA" if "transparency" in img.info or img.mode in ("LA", "P") else "RGB")
        img.thumbnail((MAX_IMAGE_SIDE, MAX_IMAGE_SIDE))
        out = io.BytesIO()
        img.save(out, "WEBP", quality=82, method=6)  # re-encoding also strips EXIF/location data
        return out.getvalue(), img.width, img.height
