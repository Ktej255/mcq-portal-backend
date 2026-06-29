"""Re-export shim for the Optional platform's prompt/schema layer.

The strict-JSON schemas, prompt builders, and parse/validate helpers that used
to live here have been MOVED into the shared, subject-neutral evaluation core
(:mod:`app.core.evaluation.schema` + :mod:`app.core.evaluation.prompts`) so that
both the Optional platform and the GS LMS can reuse one engine
(behavior-preserving refactor — Requirement 19).

This module re-exports those symbols so existing imports such as
``from app.core.optional.prompts import EvaluationReportSchema`` keep working
unchanged. Nothing here references GS Geography modules (Requirement 2 /
Property 9).
"""
from __future__ import annotations

# Schemas, constants, and the honesty/anti-gaming invariants.
from app.core.evaluation.schema import (  # noqa: F401  (re-export)
    JSON_MIME_TYPE,
    LOW_TEMPERATURE,
    RECALL_CLASSIFICATIONS,
    REQUIRED_EVALUATION_SECTIONS,
    ConceptClassification,
    EvaluationReportSchema,
    EvaluationSection,
    HintSchema,
    RecallMatchSchema,
    SchemaValidationError,
)

# Prompt builders + parse/validate helpers (incl. private helpers historically
# importable from this module).
from app.core.evaluation.prompts import (  # noqa: F401  (re-export)
    _coerce_text,
    _format_concept_checklist,
    _format_required_sections,
    _load_json_object,
    _SECTION_GUIDANCE,
    build_evaluation_request,
    build_hint_request,
    build_recall_match_request,
    parse_evaluation_report,
    parse_hint,
    parse_recall_match,
)

__all__ = [
    # constants
    "LOW_TEMPERATURE",
    "JSON_MIME_TYPE",
    "REQUIRED_EVALUATION_SECTIONS",
    "RECALL_CLASSIFICATIONS",
    # errors
    "SchemaValidationError",
    # schemas
    "EvaluationSection",
    "EvaluationReportSchema",
    "ConceptClassification",
    "RecallMatchSchema",
    "HintSchema",
    # builders
    "build_evaluation_request",
    "build_recall_match_request",
    "build_hint_request",
    # parsers
    "parse_evaluation_report",
    "parse_recall_match",
    "parse_hint",
]
