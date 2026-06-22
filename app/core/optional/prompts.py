"""Prompt builders + strict JSON schemas for evaluation & recall (Task 3.3).

This module is the prompt/contract layer for the two LLM-backed subsystems of
the Optional platform:

* **Answer evaluation** (design "Answer-evaluation pipeline", R8/R9): turn a
  student's answer + rubric into a *complete* evaluation report whose shape is
  fixed. If the model cannot produce a section it must name that section in
  ``incomplete_sections`` rather than silently dropping it — this is what makes
  report-completeness honesty (design **Property 6** / R9.2, R9.4) representable
  and checkable.
* **Recall concept-matching + adaptive hinting** (design "Recall-LMS loop",
  R13/R14): classify each author-defined concept as ``recalled`` / ``partial`` /
  ``missed`` with **paraphrase evidence in the student's own words**, explicitly
  rejecting verbatim echoes of the segment script as evidence (anti-gaming,
  design **Property 5** / R14.7). Low temperature gives the determinism basis
  for the same-transcript-same-score guarantee (design **Property 4** / R14.6).

Design decisions encoded here:
    - Builders route through the **existing inference gateway contract**
      (:class:`app.core.inference.contracts.InferenceRequest`); they set a LOW
      temperature on the request and request ``application/json`` output. They
      return request objects + schemas only — **no live model is called here**
      (the answer-evaluation / recall services in later tasks send them).
    - The strict JSON schemas are pydantic models, and each subsystem has a
      ``parse_*`` helper that validates raw model output and raises a clear
      :class:`SchemaValidationError` on malformed/missing-field output, so
      callers can flag ``incomplete_sections`` (or reject a turn) rather than
      trusting bad output.

This module performs no I/O and references no GS Geography modules (Requirement
2 / Property 9).
"""
from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Union

from pydantic import BaseModel, Field, ValidationError, field_validator, model_validator

from app.core.inference.contracts import InferenceRequest, InferenceResponse


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
# Low temperature for consistency / determinism basis (R14.6 / Property 4) and
# stable, repeatable evaluation feedback (R9.2). 0.0 = maximally deterministic.
LOW_TEMPERATURE: float = 0.0

# Strict JSON output through the existing gateway request contract.
JSON_MIME_TYPE: str = "application/json"

# The fixed set of required evaluation-report sections (design "Answer-evaluation
# pipeline" — a report always carries this fixed shape; R9.2). Each maps to a
# short instruction describing what an offline UPSC evaluator assesses there.
# The model must produce every one of these OR name it in ``incomplete_sections``
# (Property 6 / R9.4). Ordered for stable prompt rendering.
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

_SECTION_GUIDANCE: Dict[str, str] = {
    "introduction": "Assess how well the introduction frames the demand of the question.",
    "body": "Assess argument depth, relevance, and substantiation in the body.",
    "conclusion": "Assess whether the conclusion is balanced, forward-looking, and on-demand.",
    "content_coverage": "Judge coverage of the expected points against the rubric.",
    "examiner_keywords": "Identify examiner/technical keywords used well and those missed.",
    "answer_language": "Assess answer-language phrasing, precision, and exam-appropriate tone.",
    "structure_and_presentation": "Assess flow, segmentation, headings/sub-headings, and readability.",
    "value_addition": "Assess diagrams, maps, data, examples and case studies used as value addition.",
    "strengths": "List the concrete strengths of this answer.",
    "areas_for_improvement": "List concrete, actionable improvements.",
    "overall_assessment": "Give an overall qualitative assessment of the answer.",
}

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
    """Strict schema the evaluation model output must conform to (R9.2/R9.4).

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
    """Per-concept recall classification with own-words evidence (R14.5/R14.7).

    ``classification`` is one of :data:`RECALL_CLASSIFICATIONS`. For ``recalled``
    or ``partial`` the model must supply ``evidence`` — a paraphrase **in the
    student's own words**. ``verbatim_echo`` flags that the supplied evidence
    merely repeats the segment script; when true the evidence does not count as
    recall (anti-gaming, design **Property 5** / R14.7) and the classification
    is forced to ``missed`` by the validator.
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
    """Strict schema for the recall concept-matching model output (R14.1/R14.7).

    Carries one :class:`ConceptClassification` per concept in the checklist. The
    scoring math (``Σ weight × match_factor``) lives in the recall service
    (Task 12.3); this schema only guarantees a well-formed, anti-gaming-checked
    classification payload to compute it from.
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
    """Strict schema for a single adaptive Socratic hint (R14.2/R14.4).

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
# Prompt builders
# ---------------------------------------------------------------------------
def _format_required_sections() -> str:
    """Render the fixed report sections + guidance as a stable prompt block."""
    lines = []
    for name in REQUIRED_EVALUATION_SECTIONS:
        lines.append(f'- "{name}": {_SECTION_GUIDANCE.get(name, "")}')
    return "\n".join(lines)


_EVALUATION_SYSTEM_INSTRUCTION = (
    "You are a senior UPSC answer evaluator. You assess civil-services optional "
    "answers strictly against the provided rubric and produce structured, "
    "actionable feedback. You output ONLY valid JSON conforming to the requested "
    "schema. If you cannot produce a required section, you MUST name it in "
    "'incomplete_sections' rather than inventing content or silently omitting it."
)


def build_evaluation_request(
    answer_text: str,
    rubric: str,
    *,
    required_sections: Sequence[str] = REQUIRED_EVALUATION_SECTIONS,
    question: Optional[str] = None,
) -> InferenceRequest:
    """Build a gateway request for a complete answer-evaluation report (R9.2).

    The prompt instructs the model to return STRICT JSON matching
    :class:`EvaluationReportSchema`: the fixed report sections plus an
    ``incomplete_sections`` array naming any section it cannot produce
    (Property 6 / R9.4). Uses LOW temperature for consistent feedback.

    Returns an :class:`InferenceRequest`; it is NOT sent here.
    """
    sections_block = "\n".join(
        f'- "{name}": {_SECTION_GUIDANCE.get(name, "")}' for name in required_sections
    )
    question_block = f"QUESTION:\n{question}\n\n" if question else ""

    prompt = (
        f"{question_block}"
        "RUBRIC (evaluate strictly against this):\n"
        f"{rubric}\n\n"
        "STUDENT ANSWER:\n"
        f"{answer_text}\n\n"
        "TASK:\n"
        "Evaluate the answer and return a JSON object with exactly these keys: "
        '"sections", "incomplete_sections", "overall_score".\n'
        '- "sections": an object whose keys are drawn ONLY from the required '
        "section list below; each value is an object {\"feedback\": string, "
        "\"score\": number 0-10 (optional)}.\n"
        '- "incomplete_sections": an array listing EXACTLY the required sections '
        "you cannot produce. Every required section must appear either as a key "
        'in "sections" OR in "incomplete_sections" (never both, never neither).\n'
        '- "overall_score": a number 0-100 (optional).\n'
        "Do NOT present a partial section as complete; if unsure, flag it "
        "incomplete.\n\n"
        "REQUIRED SECTIONS:\n"
        f"{sections_block}\n\n"
        "Return ONLY the JSON object, no prose, no markdown fences."
    )

    return InferenceRequest(
        prompt=prompt,
        system_instruction=_EVALUATION_SYSTEM_INSTRUCTION,
        temperature=LOW_TEMPERATURE,
        response_mime_type=JSON_MIME_TYPE,
    )


_RECALL_SYSTEM_INSTRUCTION = (
    "You are an exacting recall assessor for an interactive learning system. You "
    "decide, for each author-defined concept, whether the student genuinely "
    "recalled it, partially recalled it, or missed it. You require the student to "
    "demonstrate understanding IN THEIR OWN WORDS. You MUST reject, as evidence, "
    "any passage that merely repeats the segment script verbatim or near-verbatim "
    "— mark such a concept as missed and set verbatim_echo true. You output ONLY "
    "valid JSON conforming to the requested schema."
)


def _format_concept_checklist(
    concept_checklist: Sequence[Mapping[str, Any]],
) -> str:
    """Render the segment's concept checklist (list of {concept, weight})."""
    lines = []
    for idx, item in enumerate(concept_checklist, start=1):
        concept = str(item.get("concept", "")).strip()
        weight = item.get("weight")
        weight_str = f" (weight {weight})" if weight is not None else ""
        lines.append(f"{idx}. {concept}{weight_str}")
    return "\n".join(lines)


def build_recall_match_request(
    transcript: str,
    concept_checklist: Sequence[Mapping[str, Any]],
    *,
    segment_script: Optional[str] = None,
) -> InferenceRequest:
    """Build a gateway request for recall concept-matching (R14.1/R14.7).

    Instructs the model to classify each checklist concept as
    ``recalled``/``partial``/``missed`` WITH paraphrase evidence in the student's
    own words, and to REJECT verbatim echoes of the segment script as evidence
    (anti-gaming, design **Property 5**). Returns STRICT JSON matching
    :class:`RecallMatchSchema`. Uses LOW temperature for determinism
    (design **Property 4** / R14.6).

    ``segment_script`` (when supplied) is given to the model as the reference
    text against which verbatim echoes are detected and rejected.

    Returns an :class:`InferenceRequest`; it is NOT sent here.
    """
    checklist_block = _format_concept_checklist(concept_checklist)
    script_block = (
        "SEGMENT SCRIPT (reference — reject evidence that merely repeats this "
        "text verbatim or near-verbatim):\n"
        f"{segment_script}\n\n"
        if segment_script
        else ""
    )

    prompt = (
        f"{script_block}"
        "STUDENT TRANSCRIPT (what the student said they understood):\n"
        f"{transcript}\n\n"
        "CONCEPT CHECKLIST (classify EACH concept):\n"
        f"{checklist_block}\n\n"
        "TASK:\n"
        'Return a JSON object {"concepts": [...]} with one entry per checklist '
        "concept, in checklist order. Each entry is "
        '{"concept": string (the checklist concept text), '
        '"classification": one of "recalled" | "partial" | "missed", '
        '"evidence": the student\'s OWN-WORDS paraphrase that demonstrates recall '
        '(empty string if missed), '
        '"verbatim_echo": boolean}.\n'
        "Rules:\n"
        "- Evidence MUST be in the student's own words. If the student merely "
        "repeats the segment script verbatim or near-verbatim, set "
        '"verbatim_echo": true and classify that concept as "missed" — verbatim '
        "repetition is NOT recall.\n"
        '- Use "partial" when the student shows incomplete or imprecise '
        "understanding.\n"
        "Return ONLY the JSON object, no prose, no markdown fences."
    )

    return InferenceRequest(
        prompt=prompt,
        system_instruction=_RECALL_SYSTEM_INSTRUCTION,
        temperature=LOW_TEMPERATURE,
        response_mime_type=JSON_MIME_TYPE,
    )


_HINT_SYSTEM_INSTRUCTION = (
    "You are a Socratic teacher in an interactive recall session. You help a "
    "student remember a concept they missed by giving ONE short cue or guiding "
    "question. You NEVER reveal or state the answer; you only nudge the student "
    "toward recalling it themselves. You output ONLY valid JSON conforming to "
    "the requested schema."
)


def build_hint_request(
    missed_concepts: Sequence[Union[str, Mapping[str, Any]]],
    prior_responses: Sequence[str],
) -> InferenceRequest:
    """Build a gateway request for a single adaptive Socratic hint (R14.2/R14.4).

    Given the missed concepts and the student's prior responses, instructs the
    model to produce ONE Socratic hint that cues a missed concept WITHOUT
    revealing the answer. Returns STRICT JSON matching :class:`HintSchema`. Uses
    LOW temperature for consistency.

    Returns an :class:`InferenceRequest`; it is NOT sent here.
    """
    def _concept_text(c: Union[str, Mapping[str, Any]]) -> str:
        if isinstance(c, Mapping):
            return str(c.get("concept", "")).strip()
        return str(c).strip()

    missed_block = "\n".join(
        f"- {_concept_text(c)}" for c in missed_concepts if _concept_text(c)
    ) or "- (none)"
    prior_block = "\n".join(
        f"- {str(r).strip()}" for r in prior_responses if str(r).strip()
    ) or "- (none yet)"

    prompt = (
        "MISSED CONCEPTS (the student has not yet recalled these):\n"
        f"{missed_block}\n\n"
        "STUDENT'S PRIOR RESPONSES (build on these; do not repeat what they "
        "already covered):\n"
        f"{prior_block}\n\n"
        "TASK:\n"
        "Pick ONE missed concept and craft a single Socratic hint that nudges the "
        "student toward recalling it. The hint MUST be a cue or guiding question. "
        "Do NOT reveal, state, define, or name the answer. Do NOT give the concept "
        "away.\n"
        'Return ONLY a JSON object {"hint": string, "target_concept": string}, '
        "no prose, no markdown fences."
    )

    return InferenceRequest(
        prompt=prompt,
        system_instruction=_HINT_SYSTEM_INSTRUCTION,
        temperature=LOW_TEMPERATURE,
        response_mime_type=JSON_MIME_TYPE,
    )


# ---------------------------------------------------------------------------
# Parse / validate helpers
# ---------------------------------------------------------------------------
def _coerce_text(raw: Union[str, InferenceResponse, Any]) -> str:
    """Extract the JSON text from a raw string or an ``InferenceResponse``."""
    if isinstance(raw, InferenceResponse):
        return raw.text or ""
    if isinstance(raw, str):
        return raw
    # Be permissive about response-like objects exposing ``.text``.
    text = getattr(raw, "text", None)
    if isinstance(text, str):
        return text
    raise SchemaValidationError(
        f"unsupported model output type: {type(raw).__name__}"
    )


def _load_json_object(raw: Union[str, InferenceResponse, Any]) -> Dict[str, Any]:
    """Parse model output into a JSON object, tolerating ```json fences.

    Raises :class:`SchemaValidationError` for empty output, invalid JSON, or a
    top-level value that is not a JSON object.
    """
    text = _coerce_text(raw).strip()
    if not text:
        raise SchemaValidationError("model output was empty")

    # Strip a leading/trailing markdown code fence if the model added one.
    if text.startswith("```"):
        # Remove the opening fence line (``` or ```json) and trailing fence.
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip().startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        raise SchemaValidationError(f"model output was not valid JSON: {exc}") from exc

    if not isinstance(data, dict):
        raise SchemaValidationError(
            f"expected a JSON object at the top level, got {type(data).__name__}"
        )
    return data


def parse_evaluation_report(
    raw: Union[str, InferenceResponse, Any],
) -> EvaluationReportSchema:
    """Validate raw evaluation output into :class:`EvaluationReportSchema`.

    Raises :class:`SchemaValidationError` on malformed JSON or any schema
    violation (unknown/missing sections, empty section feedback, etc.) so the
    caller can flag the report as incomplete rather than trust bad output (R9.4).
    """
    data = _load_json_object(raw)
    try:
        return EvaluationReportSchema(**data)
    except ValidationError as exc:
        raise SchemaValidationError(
            f"evaluation report failed schema validation: {exc}"
        ) from exc


def parse_recall_match(
    raw: Union[str, InferenceResponse, Any],
) -> RecallMatchSchema:
    """Validate raw recall-match output into :class:`RecallMatchSchema`.

    Applies the anti-gaming rule (verbatim echoes forced to ``missed``, P5) and
    raises :class:`SchemaValidationError` on malformed/invalid output.
    """
    data = _load_json_object(raw)
    try:
        return RecallMatchSchema(**data)
    except ValidationError as exc:
        raise SchemaValidationError(
            f"recall match failed schema validation: {exc}"
        ) from exc


def parse_hint(raw: Union[str, InferenceResponse, Any]) -> HintSchema:
    """Validate raw hint output into :class:`HintSchema`.

    Raises :class:`SchemaValidationError` on malformed/invalid output.
    """
    data = _load_json_object(raw)
    try:
        return HintSchema(**data)
    except ValidationError as exc:
        raise SchemaValidationError(
            f"hint failed schema validation: {exc}"
        ) from exc


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
