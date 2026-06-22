"""PDF generation endpoints for the GS LMS Platform.

Routes (mounted under /api/v1/gs-lms; auth-gated at the package router):
* GET /geography/topics/{node_id}/pdf — Download topic PDF

The endpoint enforces the completion restriction:
- If no sections completed → 422 error
- If some sections completed → partial PDF from completed sections only
- If all 4 sections completed → full PDF

The topic must be a REVIEWED syllabus node.

Requirements traced: 8.1, 8.4, 8.5
"""

from __future__ import annotations

import re
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models.domain import User
from app.api.dependencies import get_current_user
from app.core.gs.models import GsReviewStatusEnum
from app.core.gs_lms.models import (
    GsLmsSyllabusNode,
    GsLmsContentSection,
)
from app.core.gs_lms.student_models import GsLmsStudentSectionProgress
from app.core.gs_lms.pdf_generator import (
    generate_topic_pdf,
    sections_from_db_records,
    get_content_type,
    get_file_extension,
)
from app.api.v1.gs_lms.schemas import GsLmsPdfStatusOut

router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _get_reviewed_node_or_404(db: Session, node_id: int) -> GsLmsSyllabusNode:
    """Fetch a REVIEWED syllabus node by ID or raise 404."""
    node = (
        db.query(GsLmsSyllabusNode)
        .filter(
            GsLmsSyllabusNode.id == node_id,
            GsLmsSyllabusNode.review_status == GsReviewStatusEnum.REVIEWED,
        )
        .one_or_none()
    )
    if node is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Topic not found",
        )
    return node


def _get_completed_section_ids(
    db: Session, student_id: int, node_id: int
) -> set[int]:
    """Return set of section IDs the student has completed for this topic."""
    progress_rows = (
        db.query(GsLmsStudentSectionProgress)
        .filter(
            GsLmsStudentSectionProgress.student_id == student_id,
            GsLmsStudentSectionProgress.syllabus_node_id == node_id,
            GsLmsStudentSectionProgress.completed == True,  # noqa: E712
        )
        .all()
    )
    return {row.section_id for row in progress_rows}


def _sanitize_filename(title: str) -> str:
    """Sanitize a title for use as a filename (remove unsafe characters)."""
    # Replace non-alphanumeric chars (except spaces, hyphens, underscores) with empty string
    sanitized = re.sub(r'[^\w\s\-]', '', title, flags=re.UNICODE)
    # Replace whitespace with underscore
    sanitized = re.sub(r'\s+', '_', sanitized.strip())
    return sanitized or "topic"


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/geography/topics/{node_id}/pdf")
def download_topic_pdf(
    node_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> Any:
    """Download a PDF for a topic's completed content sections.

    Completion restriction (Requirement 8.4):
    - If no sections completed → 422 error
    - If some sections completed → generates partial PDF from completed sections only
    - If all 4 sections completed → generates full PDF with all sections

    The topic must be a REVIEWED syllabus node.

    Returns a binary response with appropriate Content-Type and
    Content-Disposition headers for download.

    Validates: Requirements 8.1, 8.4, 8.5
    """
    # Fetch REVIEWED node or 404
    node = _get_reviewed_node_or_404(db, node_id)

    # Get all REVIEWED sections for this topic
    all_sections = (
        db.query(GsLmsContentSection)
        .filter(
            GsLmsContentSection.syllabus_node_id == node_id,
            GsLmsContentSection.review_status == GsReviewStatusEnum.REVIEWED,
        )
        .order_by(GsLmsContentSection.display_order)
        .all()
    )

    # Get student's completed section IDs for this topic
    completed_ids = _get_completed_section_ids(db, current_user.id, node_id)

    # Filter to completed sections only
    completed_sections = [s for s in all_sections if s.id in completed_ids]

    # If no sections completed → 422
    if not completed_sections:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No sections completed for this topic. Complete at least one section before downloading.",
        )

    # Convert DB records to PDF generator Section dataclasses
    pdf_sections = sections_from_db_records(completed_sections)

    # Generate PDF (or HTML fallback)
    pdf_bytes = generate_topic_pdf(
        sections=pdf_sections,
        topic_title=node.title,
        subject_name="GS Geography",
    )

    # Determine content type and file extension
    content_type = get_content_type(pdf_bytes)
    extension = get_file_extension(pdf_bytes)

    # Build download filename
    filename = f"{_sanitize_filename(node.title)}{extension}"

    return Response(
        content=pdf_bytes,
        media_type=content_type,
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
        },
    )
