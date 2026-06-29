"""Strict JSON schemas + shared constants/errors for the evaluation core.

Moved verbatim (behavior-preserving) from ``app.core.optional.prompts`` into the
shared, subject-neutral evaluation core (design "Shared evaluation core" — R1.1,
R19.1/R19.2). This module is the schema/contract layer for the LLM-backed
subsystems:

* **Answer evaluation** — :class:`EvaluationReportSchema` encodes the
  report-completeness honesty invariant (design **Property 6** / R6): a report is
  "complete" only when every required section is produced; any section the model
  cannot produce is named in ``incomplete_sections`` rather than fabricated.
* **Recall concept-matching + hinting** — :class:`RecallMatchSchema` /
  :class:`ConceptClassification` / :class:`HintSchema` carry the anti-gaming rule
  (verbatim echoes forced to ``missed``, design **Property 5**).

No I/O. References no GS or Optional modules (Requirement 2 / Property 9).
"""
from __future__ import annotations

from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Low temperature for consistency / determinism basis and stable, repeatable
# evaluation feedback. 0.0 = maximally deterministic.
LOW_TEMPERATURE: float = 0.0

# Strict JSON output through the existing gateway request contract.
JSON_MIME_TYPE: str = "application/json"

# The fixed set of required evaluation-report sections. The model must produce
# every one of these OR name it in ``incomplete_sections`` (Property 6 / R6).
# Ordered for stable prompt rendering.
REQUIRED_EVALUATION_SECTIONS: tuple[str, ...] = (
    "introduction",
    "body",
    "conclusion",
    "content_coverage",
    "examiner_keywords",
    "answer_language",
    "structure_and_presentation",
    "value_addition",
    "strengths",
    "areas_for_improvement",
    "overall_assessment",
)

# Allowed recall classifications (design Recall scoring step 2).
RECALL_CLASSIFICATIONS: tuple[str, ...] = ("recalled", "partial", "missed")


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------
class SchemaValidationError(ValueError):
    """Raised when raw model output cannot be parsed into the strict schema.

    Carries a human-readable message so callers can surface a clear failure
    (e.g. flag the report as incomplete, or reject the recall turn) instead of
    trusting malformed model output.
    """


# ---------------------------------------------------------------------------
# Strict JSON schemas — Answer evaluation
# ---------------------------------------------------------------------------
class EvaluationSection(BaseModel):
    """Feedback for a single evaluation-report section.

    ``feedback`` is required and must be non-empty (an empty section is not a
    produced section — if the model cannot produce it, it belongs in
    ``incomplete_sections`` instead). ``score`` is an optional 0..10 rating.
    """

    model_config = {"extra": "forbid"}

    feedback: str
    score: Optional[float] = Field(default=None, ge=0.0, le=10.0)

    @field_validator("feedback")
    @classmethod
    def _feedback_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("section feedback must be a non-empty string")
        return v


class EvaluationReportSchema(BaseModel):
    """Strict schema the evaluation model output must conform to (R6).

    Invariants enforced (design **Property 6**):
        * keys of ``sections`` and entries of ``incomplete_sections`` are drawn
          only from :data:`REQUIRED_EVALUATION_SECTIONS` (no unknown sections);
        * every required section is accounted for — either produced in
          ``sections`` or named in ``incomplete_sections`` (never both, never
          neither);
        * a report is "complete" iff ``incomplete_sections`` is empty.
    """

    model_config = {"extra": "forbid"}

    sections: Dict[str, EvaluationSection] = Field(default_factory=dict)
    incomplete_sections: List[str] = Field(default_factory=list)
    overall_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)

    @model_validator(mode="after")
    def _validate_section_coverage(self) -> "EvaluationReportSchema":
        required = set(REQUIRED_EVALUATION_SECTIONS)
        produced = set(self.sections.keys())
        incomplete = set(self.incomplete_sections)

        unknown_produced = produced - required
        if unknown_produced:
            raise ValueError(f"unknown produced sections: {sorted(unknown_produced)}")

        unknown_incomplete = incomplete - required
        if unknown_incomplete:
            raise ValueError(f"unknown incomplete sections: {sorted(unknown_incomplete)}")

        overlap = produced & incomplete
        if overlap:
            raise ValueError(
                f"sections cannot be both produced and incomplete: {sorted(overlap)}"
            )

        accounted = produced | incomplete
        missing = required - accounted
        if missing:
            raise ValueError(
                f"sections neither produced nor flagged incomplete: {sorted(missing)}"
            )

        # Normalise to a stable, deduplicated order matching the canonical list.
        self.incomplete_sections = [
            s for s in REQUIRED_EVALUATION_SECTIONS if s in incomplete
        ]
        return self

    @property
    def is_complete(self) -> bool:
        """A report is complete only when no sections are missing (Property 6)."""
        return not self.incomplete_sections


# ---------------------------------------------------------------------------
# Strict JSON schemas — Recall concept matching
# ---------------------------------------------------------------------------
class ConceptClassification(BaseModel):
    """Per-concept recall classification with own-words evidence.

    ``classification`` is one of :data:`RECALL_CLASSIFICATIONS`. For ``recalled``
    or ``partial`` the model must supply ``evidence`` — a paraphrase **in the
    student's own words**. ``verbatim_echo`` flags that the supplied evidence
    merely repeats the segment script; when true the evidence does not count as
    recall (anti-gaming, design **Property 5**) and the classification is forced
    to ``missed`` by the validator.
    """

    model_config = {"extra": "forbid"}

    concept: str
    classification: str
    evidence: str = ""
    verbatim_echo: bool = False

    @field_validator("concept")
    @classmethod
    def _concept_non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("concept must be a non-empty string")
        return v

    @field_validator("classification")
    @classmethod
    def _classification_allowed(cls, v: str) -> str:
        if v not in RECALL_CLASSIFICATIONS:
            raise ValueError(
                f"classification must be one of {RECALL_CLASSIFICATIONS}, got {v!r}"
            )
        return v

    @model_validator(mode="after")
    def _evidence_consistency(self) -> "ConceptClassification":
        # Anti-gaming: verbatim echo is never accepted as recall evidence; such a
        # concept is treated as missed regardless of the model's optimism (P5).
        if self.verbatim_echo:
            self.classification = "missed"
            self.evidence = ""
            return self
        # A recalled/partial concept must carry own-words evidence.
        if self.classification in ("recalled", "partial") and not self.evidence.strip():
            raise ValueError(
                "recalled/partial concepts require non-empty own-words evidence"
            )
        if self.classification == "missed":
            # Missed concepts carry no positive evidence.
            self.evidence = ""
        return self


class RecallMatchSchema(BaseModel):
    """Strict schema for the recall concept-matching model output.

    Carries one :class:`ConceptClassification` per concept in the checklist. The
    scoring math (``Σ weight × match_factor``) lives in the recall service; this
    schema only guarantees a well-formed, anti-gaming-checked classification
    payload to compute it from.
    """

    model_config = {"extra": "forbid"}

    concepts: List[ConceptClassification] = Field(default_factory=list)

    @field_validator("concepts")
    @classmethod
    def _at_least_one_concept(cls, v: List[ConceptClassification]):
        if not v:
            raise ValueError("recall match must classify at least one concept")
        return v


# ---------------------------------------------------------------------------
# Strict JSON schema — Adaptive Socratic hint
# ---------------------------------------------------------------------------
class HintSchema(BaseModel):
    """Strict schema for a single adaptive Socratic hint.

    ``hint`` cues a missed concept without revealing the answer; ``target_concept``
    names the missed concept it nudges toward.
    """

    model_config = {"extra": "forbid"}

    hint: str
    target_concept: str

    @field_validator("hint", "target_concept")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not isinstance(v, str) or not v.strip():
            raise ValueError("hint fields must be non-empty strings")
        return v


# ---------------------------------------------------------------------------
# Subject-neutral DTOs (engine input + assembled report) — R1.1, R1.5, R7, R8
# ---------------------------------------------------------------------------
class MarkingScheme(BaseModel):
    """Marks/length context for an evaluation (R7, R8).

    ``max_marks`` is the question's real mark allotment (e.g. 10 or 15) used to
    marks-normalize the score. ``expected_dimensions`` optionally lists the
    rubric dimensions the answer is expected to address; ``reference_answer`` is
    the model answer used for grounding (R7.3). All optional so a free-form
    practice question (no PYQ) can still be evaluated (R9.5).
    """

    model_config = {"extra": "forbid"}

    max_marks: Optional[int] = Field(default=None, ge=0)
    expected_dimensions: List[str] = Field(default_factory=list)


class EvaluationReport(BaseModel):
    """Subject-neutral assembled evaluation report returned by the engine (R1.5).

    Wraps the strict model-output sections (honesty invariant preserved) and
    adds marks-normalized scoring, length-bias fields, factual-accuracy payload,
    and provider/usage bookkeeping. Its top-level SHAPE is identical regardless
    of which rubric strategy produced it (R1.5).
    """

    model_config = {"extra": "forbid"}

    sections: Dict[str, EvaluationSection] = Field(default_factory=dict)
    incomplete_sections: List[str] = Field(default_factory=list)
    overall_score: Optional[float] = Field(default=None, ge=0.0, le=100.0)
    # Marks-normalized scoring (R7.1/R7.2).
    marks_awarded: Optional[float] = None
    max_marks: Optional[int] = None
    # Length-bias reporting (R8.4).
    word_count: Optional[int] = None
    word_limit: Optional[int] = None
    # Factual-accuracy assessment: unsupported/contradicted claims (R7.5/R7.6).
    factual_accuracy: Optional[Dict[str, object]] = None
    # Value-addition assessment reflecting diagrams/maps (R13.3).
    value_addition: Optional[Dict[str, object]] = None
    # Provider/usage bookkeeping (R18.5).
    provider_key: Optional[str] = None
    token_usage: Optional[int] = None

    @property
    def is_complete(self) -> bool:
        """A report is complete only when no sections are missing (Property 6)."""
        return not self.incomplete_sections


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
    # DTOs
    "MarkingScheme",
    "EvaluationReport",
]
