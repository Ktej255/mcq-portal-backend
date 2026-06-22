# Optional Subjects Platform - API router package
#
# Aggregates all optional-platform sub-routers (content, PYQ, evaluation,
# recall, progress, entitlement, ...) under a single APIRouter that is mounted
# at /api/v1/optional in app.main. Every route in this package is auth-gated
# via the existing authentication dependency (app.api.dependencies).
#
# Hard isolation constraint (Requirement 2 / design Property 9): this package
# MUST NOT import from, reference, or modify GS Geography (/upsc/geography)
# modules or routes.

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.api.v1.optional import health
from app.api.v1.optional import content
from app.api.v1.optional import pyqs
from app.api.v1.optional import practice
from app.api.v1.optional import transcribe
from app.api.v1.optional import ocr
from app.api.v1.optional import answers
from app.api.v1.optional import progress
from app.api.v1.optional import recall
from app.api.v1.optional import selection
from app.api.v1.optional import mapping
from app.api.v1.optional import subject_config
from app.api.v1.optional import review
from app.api.v1.optional import current_affairs

# All optional-platform routes require authentication. Declaring the dependency
# at the aggregate level enforces auth-gating uniformly across every sub-router.
router = APIRouter(dependencies=[Depends(get_current_user)])

router.include_router(health.router, tags=["optional"])
router.include_router(content.router, tags=["optional"])
router.include_router(pyqs.router, tags=["optional"])
router.include_router(practice.router, tags=["optional"])
router.include_router(transcribe.router, tags=["optional"])
router.include_router(ocr.router, tags=["optional"])
router.include_router(answers.router, tags=["optional"])
router.include_router(progress.router, tags=["optional"])
router.include_router(recall.router, tags=["optional"])
router.include_router(selection.router, tags=["optional"])
router.include_router(mapping.router, tags=["optional"])
router.include_router(subject_config.router, tags=["optional"])
router.include_router(review.router, tags=["optional"])
router.include_router(current_affairs.router, tags=["optional"])
