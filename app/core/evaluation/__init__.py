"""Shared, subject-neutral answer-evaluation core.

This package holds the evaluation machinery that is reused by BOTH the Optional
Subjects platform (``app.core.optional``) and the GS LMS (``app.core.gs_lms``).
It is intentionally subject-neutral: it imports nothing from either domain, and
both domains depend only on this package's public interface (design
"Domain isolation" — Requirement 2).

Modules:
    schema    — strict-JSON pydantic schemas + the report-completeness honesty
                invariant + shared constants/errors.
    prompts   — gateway prompt builders + parse/validate helpers.

The Optional modules ``app.core.optional.prompts`` and
``app.core.optional.providers.evaluation`` re-export from here so existing
imports keep working unchanged while the implementation lives in one place
(behavior-preserving refactor — Requirement 19).
"""
