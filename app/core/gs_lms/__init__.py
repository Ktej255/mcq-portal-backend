"""GS LMS (General Studies Learning Management System) backend domain.

This package extends the existing GS Geography guided-study system into a full
LMS experience with structured topic-based navigation, progressive content
delivery, PYQ integration, sequential MCQ practice, AI discussion mode, gap
tracking, daily planning, and PDF generation.

Architecture mirrors the Optional Subjects platform: a self-referencing weighted
syllabus tree, review-gated content, ownership-scoped student activity — all
within a new ``gs_lms_`` table namespace that extends (never replaces) the
existing ``gs_subjects`` / ``gs_day_lessons`` store.

Domain isolation: this package has zero cross-imports from ``app.core.optional``.
Shared abstractions (review enum, audit mixin) come from shared base modules.
"""

MODULE_NAME = "gs_lms"

__all__ = ["MODULE_NAME"]
