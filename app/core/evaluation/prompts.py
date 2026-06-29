"""Prompt builders + parse/validate helpers for the evaluation core.

Moved verbatim (behavior-preserving) from ``app.core.optional.prompts`` into the
shared, subject-neutral evaluation core (R1.1, R19.1/R19.2). Builders route
through the existing inference gateway contract
(:class:`app.core.inference.contracts.InferenceRequest`), set a LOW temperature,
and request ``application/json`` output. They return request objects only — no
live model is called here. Parsers validate raw model output against the strict
schemas in :mod:`app.core.evaluation.schema` and raise
:class:`SchemaValidationError` on malformed output.

No I/O beyond constructing requests. References no GS or Optional modules
(Requirement 2 / Property 9).
"""
from __future__ import annotations

import json
from typing import Any, Dict, Mapping, Optional, Sequence, Union

from pydantic import ValidationError

from app.core.inference.contracts import InferenceRequest, InferenceResponse
from app.core.evaluation.schema import (
    JSON_MIME_TYPE,
    LOW_TEMPERATURE,
    REQUIRED_EVALUATION_SECTIONS,
    EvaluationReportSchema,
    HintSchema,
    RecallMatchSchema,
    SchemaValidationError,
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
    """Build a gateway request for a complete answer-evaluation report (R6).

    The prompt instructs the model to return STRICT JSON matching
    :class:`EvaluationReportSchema`: the fixed report sections plus an
    ``incomplete_sections`` array naming any section it cannot produce
    (Property 6). Uses LOW temperature for consistent feedback.

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
    """Build a gateway request for recall concept-matching.

    Instructs the model to classify each checklist concept as
    ``recalled``/``partial``/``missed`` WITH paraphrase evidence in the student's
    own words, and to REJECT verbatim echoes of the segment script as evidence
    (anti-gaming, design **Property 5**). Returns STRICT JSON matching
    :class:`RecallMatchSchema`. Uses LOW temperature for determinism.

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
    """Build a gateway request for a single adaptive Socratic hint.

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
    caller can flag the report as incomplete rather than trust bad output (R6).
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
    # builders
    "build_evaluation_request",
    "build_recall_match_request",
    "build_hint_request",
    # parsers
    "parse_evaluation_report",
    "parse_recall_match",
    "parse_hint",
]
