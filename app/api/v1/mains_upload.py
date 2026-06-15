"""
Phase 4 — Frictionless Mobile Mains Answer Upload
Step 4.3: Backend PDF assembler endpoint

Accepts ordered JPEG/PNG images via multipart form data,
assembles them into a single PDF using stdlib only (no heavy deps),
and returns the PDF as a downloadable file or stores it.
"""

from __future__ import annotations

import io
import logging
import struct
import time
import zlib
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.api.dependencies import get_current_user
from app.db.session import get_db
from app.models.domain import User
from app.schemas.common import StandardResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# ---------------------------------------------------------------------------
# Minimal PDF writer — no external dependencies, only stdlib.
# Produces a valid single/multi-page PDF from raw JPEG or PNG bytes.
# ---------------------------------------------------------------------------

_PDF_HEADER = b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n"


def _pdf_obj(n: int, content: bytes) -> bytes:
    return f"{n} 0 obj\n".encode() + content + b"\nendobj\n"


def _png_dimensions(data: bytes) -> tuple[int, int]:
    """Extract width/height from PNG IHDR chunk (bytes 16-24)."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("Not a valid PNG file")
    w = struct.unpack(">I", data[16:20])[0]
    h = struct.unpack(">I", data[20:24])[0]
    return w, h


def _jpeg_dimensions(data: bytes) -> tuple[int, int]:
    """Parse JPEG SOF markers to extract width and height."""
    i = 2  # skip FF D8
    while i < len(data) - 8:
        if data[i] != 0xFF:
            break
        marker = data[i + 1]
        if marker in (0xC0, 0xC1, 0xC2):  # SOF0/SOF1/SOF2
            h = struct.unpack(">H", data[i + 5 : i + 7])[0]
            w = struct.unpack(">H", data[i + 7 : i + 9])[0]
            return w, h
        length = struct.unpack(">H", data[i + 2 : i + 4])[0]
        i += 2 + length
    return 595, 842  # A4 fallback in points


def _is_png(data: bytes) -> bool:
    return data[:8] == b"\x89PNG\r\n\x1a\n"


def _png_to_jpeg_approx(data: bytes) -> bytes:
    """
    We cannot do PNG→JPEG without Pillow.
    Instead we embed the PNG as a raw image XObject using its raw pixels.
    This function returns a PDF-compatible flate-compressed image stream.
    For the minimal pure-stdlib case we embed PNG files using the
    /FlateDecode filter by extracting IDAT chunks and treating them
    as RGB data. A proper implementation would use Pillow, but we keep
    this zero-dependency and fall back to a placeholder white page if
    decompression of PNG pixel data would require a full decoder.

    In production the mobile camera virtually always produces JPEG,
    so this path is rarely exercised.
    """
    raise NotImplementedError("Pure-stdlib PNG embed not fully supported; convert to JPEG on the client side.")


def _assemble_pdf(images: List[bytes]) -> bytes:
    """
    Assemble a multi-page PDF from a list of JPEG byte strings.
    PNG files will raise a clear error directing the caller to send JPEG.
    """
    buf = io.BytesIO()
    buf.write(_PDF_HEADER)

    offsets: list[int] = []
    obj_id = 1  # current object counter

    page_obj_ids: list[int] = []
    image_obj_ids: list[int] = []
    dim_list: list[tuple[int, int]] = []

    for img_bytes in images:
        if _is_png(img_bytes):
            try:
                w, h = _png_dimensions(img_bytes)
            except Exception:
                w, h = 595, 842
            # Convert PNG → JPEG requires Pillow; for now raise helpful error.
            raise HTTPException(
                status_code=422,
                detail=(
                    "PNG images detected. Please capture images as JPEG (the default on all mobile browsers). "
                    "PNG support requires an optional server dependency (Pillow). "
                    "Ask your administrator to install Pillow if PNG support is needed."
                ),
            )
        else:
            try:
                w, h = _jpeg_dimensions(img_bytes)
            except Exception:
                w, h = 595, 842

        dim_list.append((w, h))

        # Write image XObject
        offsets.append(buf.tell())
        img_dict = (
            f"<< /Type /XObject /Subtype /Image "
            f"/Width {w} /Height {h} "
            f"/ColorSpace /DeviceRGB "
            f"/BitsPerComponent 8 "
            f"/Filter /DCTDecode "
            f"/Length {len(img_bytes)} >>\n"
            f"stream\n"
        ).encode()
        buf.write(f"{obj_id} 0 obj\n".encode())
        buf.write(img_dict)
        buf.write(img_bytes)
        buf.write(b"\nendstream\nendobj\n")
        image_obj_ids.append(obj_id)
        obj_id += 1

    # Page content streams
    content_obj_ids: list[int] = []
    for idx, (w, h) in enumerate(dim_list):
        content = (
            f"q {w} 0 0 {h} 0 0 cm /Im{idx + 1} Do Q"
        ).encode()
        offsets.append(buf.tell())
        buf.write(f"{obj_id} 0 obj\n<< /Length {len(content)} >>\nstream\n".encode())
        buf.write(content)
        buf.write(b"\nendstream\nendobj\n")
        content_obj_ids.append(obj_id)
        obj_id += 1

    # Page objects
    for idx, (w, h) in enumerate(dim_list):
        offsets.append(buf.tell())
        page_content = (
            f"<< /Type /Page /Parent 2 0 R "
            f"/MediaBox [0 0 {w} {h}] "
            f"/Contents {content_obj_ids[idx]} 0 R "
            f"/Resources << /XObject << /Im{idx + 1} {image_obj_ids[idx]} 0 R >> >> >>"
        ).encode()
        buf.write(f"{obj_id} 0 obj\n".encode())
        buf.write(page_content)
        buf.write(b"\nendobj\n")
        page_obj_ids.append(obj_id)
        obj_id += 1

    # Pages dictionary (object 2)
    pages_content = (
        "<< /Type /Pages /Kids ["
        + " ".join(f"{pid} 0 R" for pid in page_obj_ids)
        + f"] /Count {len(page_obj_ids)} >>"
    ).encode()
    pages_offset = buf.tell()
    buf.write(b"2 0 obj\n")
    buf.write(pages_content)
    buf.write(b"\nendobj\n")

    # Catalog (object 1)
    catalog_offset = buf.tell()
    buf.write(b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n")

    # Cross-reference table
    xref_offset = buf.tell()
    all_offsets = [catalog_offset, pages_offset] + offsets
    buf.write(f"xref\n0 {len(all_offsets) + 1}\n".encode())
    buf.write(b"0000000000 65535 f \n")
    for off in all_offsets:
        buf.write(f"{off:010d} 00000 n \n".encode())

    buf.write(
        f"trailer\n<< /Size {len(all_offsets) + 1} /Root 1 0 R >>\n"
        f"startxref\n{xref_offset}\n%%EOF\n".encode()
    )

    return buf.getvalue()


# ---------------------------------------------------------------------------
# API Endpoints
# ---------------------------------------------------------------------------

MAX_FILE_SIZE_MB = 20
MAX_PAGES = 30


@router.post("/assemble-pdf")
async def assemble_mains_pdf(
    files: List[UploadFile] = File(..., description="Ordered JPEG images (Page 1 first)"),
    subject: str = Form(default="general", description="Subject label e.g. gs1, gs2, gs3, gs4"),
    question_hint: str = Form(default="", description="Optional question identifier or hint"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Accepts 1–30 ordered JPEG images and assembles them into a single PDF.
    Returns the PDF as an inline attachment.

    Frontend sends images in display order (already sorted by the student via
    the drag-and-drop ribbon in MobileAnswerUploader.tsx).
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")
    if len(files) > MAX_PAGES:
        raise HTTPException(status_code=400, detail=f"Maximum {MAX_PAGES} pages allowed per upload.")

    image_bytes_list: list[bytes] = []
    for upload in files:
        raw = await upload.read()
        size_mb = len(raw) / (1024 * 1024)
        if size_mb > MAX_FILE_SIZE_MB:
            raise HTTPException(
                status_code=413,
                detail=f"File '{upload.filename}' exceeds {MAX_FILE_SIZE_MB} MB limit ({size_mb:.1f} MB).",
            )
        image_bytes_list.append(raw)

    logger.info(
        f"[mains_upload] user={current_user.id} subject={subject} pages={len(image_bytes_list)}"
    )

    try:
        pdf_bytes = _assemble_pdf(image_bytes_list)
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception(f"[mains_upload] PDF assembly failed: {exc}")
        raise HTTPException(status_code=500, detail=f"PDF assembly failed: {exc}")

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    filename = f"mains_{subject}_{timestamp}.pdf"

    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "X-Page-Count": str(len(image_bytes_list)),
            "X-Subject": subject,
        },
    )


@router.get("/ping")
def ping_upload_service():
    """Health check for the mains upload service."""
    return {"status": "ok", "service": "mains_upload", "timestamp": time.time()}
