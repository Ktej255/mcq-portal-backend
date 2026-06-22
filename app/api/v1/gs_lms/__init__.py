# GS LMS Platform - API router package
#
# Aggregates all GS LMS sub-routers (syllabus, content, PYQ, practice,
# discussion, progress, planner, PDF, onboarding) under a single APIRouter
# that is mounted at /api/v1/gs-lms in app.main. Every route in this package
# is auth-gated via the existing authentication dependency
# (app.api.dependencies).
#
# Hard isolation constraint (design Key Decision 3 / Requirement 10.4): this
# package MUST NOT import from, reference, or modify Optional Subjects
# (app.core.optional / app.api.v1.optional) modules or routes.

from fastapi import APIRouter, Depends

from app.api.dependencies import get_current_user
from app.api.v1.gs_lms import syllabus
from app.api.v1.gs_lms import content
from app.api.v1.gs_lms import pyqs
from app.api.v1.gs_lms import practice
from app.api.v1.gs_lms import discussion
from app.api.v1.gs_lms import progress
from app.api.v1.gs_lms import planner
from app.api.v1.gs_lms import pdf
from app.api.v1.gs_lms import onboarding

# All GS LMS routes require authentication. Declaring the dependency at the
# aggregate level enforces auth-gating uniformly across every sub-router
# (Requirement 10.2 / design Property 23).
router = APIRouter(dependencies=[Depends(get_current_user)])

router.include_router(syllabus.router, tags=["gs-lms"])
router.include_router(content.router, tags=["gs-lms"])
router.include_router(pyqs.router, tags=["gs-lms"])
router.include_router(practice.router, tags=["gs-lms"])
router.include_router(discussion.router, tags=["gs-lms"])
router.include_router(progress.router, tags=["gs-lms"])
router.include_router(planner.router, tags=["gs-lms"])
router.include_router(pdf.router, tags=["gs-lms"])
router.include_router(onboarding.router, tags=["gs-lms"])
