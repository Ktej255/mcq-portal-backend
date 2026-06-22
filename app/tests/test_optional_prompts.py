"""Tests for the Optional platform evaluation/recall prompt builders (Task 3.3).

Covers:
* prompt builders include the required sections / rubric / concepts and set a
  LOW temperature on the existing gateway request contract;
* the strict JSON schema validators accept a well-formed sample and reject
  malformed / missing-field samples;
* the recall schema captures matched / partial / missed + own-words evidence and
  rejects verbatim echoes as evidence (anti-gaming, design Property 5);
* the hint builder includes missed concepts and forbids revealing the answer.

No live model is invoked — builders return request objects and the parsers run
against hand-written sample payloads.

Requirements: 9.2, 14.1, 14.6. Properties: P4, P5, P6.
"""
import importlib

import pytest

from app.core.inference.contracts import InferenceRequest, InferenceResponse
from app.core.optional.prompts import (
    JSON_MIME_TYPE,
    LOW_TEMPERATURE,
    REQUIRED_EVALUATION_SECTIONS,
    ConceptClassification,
    EvaluationReportSchema,
    EvaluationSection,
    HintSchema,
    RecallMatchSchema,
    SchemaValidationError,
    build_evaluation_request,
    build_hint_request,
    build_recall_match_request,
    parse_evaluation_report,
    parse_hint,
    parse_recall_match,
)


# ---------------------------------------------------------------------------
# Builder: answer evaluation
# ---------------------------------------------------------------------------
def test_evaluation_request_uses_gateway_contract_and_low_temperature():
    req = build_evaluation_request("my answer", "the rubric")
    assert isinstance(req, InferenceRequest)
    assert req.temperature == LOW_TEMPERATURE
    assert req.temperature <= 0.2  # "low" temperature
    assert req.response_mime_type == JSON_MIME_TYPE


def test_evaluation_request_includes_answer_rubric_and_all_sections():
    req = build_evaluation_request("ANSWER_TEXT_X", "RUBRIC_TEXT_Y", question="Q_TEXT_Z")
    assert "ANSWER_TEXT_X" in req.prompt
    assert "RUBRIC_TEXT_Y" in req.prompt
    assert "Q_TEXT_Z" in req.prompt
    # Every required report section name must appear in the prompt.
    for section in REQUIRED_EVALUATION_SECTIONS:
        assert section in req.prompt
    # And the honesty instruction (Property 6 / R9.4).
    assert "incomplete_sections" in req.prompt


# ---------------------------------------------------------------------------
# Builder: recall concept matching
# ---------------------------------------------------------------------------
def test_recall_request_low_temperature_for_determinism():
    req = build_recall_match_request("transcript", [{"concept": "c", "weight": 1.0}])
    assert isinstance(req, InferenceRequest)
    assert req.temperature == LOW_TEMPERATURE  # determinism basis (P4 / R14.6)
    assert req.response_mime_type == JSON_MIME_TYPE


def test_recall_request_includes_transcript_concepts_and_antigaming_instruction():
    checklist = [
        {"concept": "youthful stage of river", "weight": 0.5},
        {"concept": "graded profile", "weight": 0.5},
    ]
    req = build_recall_match_request(
        "TRANSCRIPT_ABC", checklist, segment_script="SEGMENT_SCRIPT_DEF"
    )
    assert "TRANSCRIPT_ABC" in req.prompt
    assert "SEGMENT_SCRIPT_DEF" in req.prompt
    for item in checklist:
        assert item["concept"] in req.prompt
    # Anti-gaming + own-words + classification vocabulary present (P5 / R14.7).
    assert "own words" in req.prompt.lower()
    assert "verbatim" in req.prompt.lower()
    for label in ("recalled", "partial", "missed"):
        assert label in req.prompt


# ---------------------------------------------------------------------------
# Builder: adaptive Socratic hint
# ---------------------------------------------------------------------------
def test_hint_request_includes_missed_concepts_and_forbids_reveal():
    req = build_hint_request(
        ["MISSED_CONCEPT_1", {"concept": "MISSED_CONCEPT_2"}],
        ["prior response one"],
    )
    assert isinstance(req, InferenceRequest)
    assert req.temperature == LOW_TEMPERATURE
    assert "MISSED_CONCEPT_1" in req.prompt
    assert "MISSED_CONCEPT_2" in req.prompt
    assert "prior response one" in req.prompt
    # Must instruct NOT to reveal the answer (R14.4) and be Socratic (R14.2).
    assert "not reveal" in req.prompt.lower() or "do not reveal" in req.prompt.lower()
    assert "socratic" in req.prompt.lower() or "socratic" in (req.system_instruction or "").lower()


# ---------------------------------------------------------------------------
# Schema: evaluation report (Property 6)
# ---------------------------------------------------------------------------
def _complete_sections() -> dict:
    return {name: {"feedback": f"feedback for {name}"} for name in REQUIRED_EVALUATION_SECTIONS}


def test_parse_evaluation_report_accepts_complete_sample():
    payload = {
        "sections": _complete_sections(),
        "incomplete_sections": [],
        "overall_score": 72.5,
    }
    report = parse_evaluation_report(__import_json(payload))
    assert isinstance(report, EvaluationReportSchema)
    assert report.is_complete is True
    assert report.incomplete_sections == []


def test_parse_evaluation_report_flags_incomplete_sections():
    sections = _complete_sections()
    # Drop two sections and declare them incomplete instead.
    del sections["value_addition"]
    del sections["conclusion"]
    payload = {
        "sections": sections,
        "incomplete_sections": ["value_addition", "conclusion"],
    }
    report = parse_evaluation_report(__import_json(payload))
    assert report.is_complete is False
    assert set(report.incomplete_sections) == {"value_addition", "conclusion"}


def test_parse_evaluation_report_rejects_missing_section_not_flagged():
    sections = _complete_sections()
    del sections["body"]  # missing AND not flagged incomplete -> invalid
    payload = {"sections": sections, "incomplete_sections": []}
    with pytest.raises(SchemaValidationError):
        parse_evaluation_report(__import_json(payload))


def test_parse_evaluation_report_rejects_section_both_produced_and_incomplete():
    payload = {
        "sections": _complete_sections(),
        "incomplete_sections": ["body"],  # body is also produced
    }
    with pytest.raises(SchemaValidationError):
        parse_evaluation_report(__import_json(payload))


def test_parse_evaluation_report_rejects_unknown_section():
    sections = _complete_sections()
    sections["made_up_section"] = {"feedback": "x"}
    payload = {"sections": sections, "incomplete_sections": []}
    with pytest.raises(SchemaValidationError):
        parse_evaluation_report(__import_json(payload))


def test_parse_evaluation_report_rejects_empty_section_feedback():
    sections = _complete_sections()
    sections["body"] = {"feedback": "   "}
    payload = {"sections": sections, "incomplete_sections": []}
    with pytest.raises(SchemaValidationError):
        parse_evaluation_report(__import_json(payload))


def test_parse_evaluation_report_rejects_malformed_json():
    with pytest.raises(SchemaValidationError):
        parse_evaluation_report("not-json-at-all {")


def test_parse_evaluation_report_rejects_empty_output():
    with pytest.raises(SchemaValidationError):
        parse_evaluation_report("")


def test_parse_evaluation_report_accepts_markdown_fenced_json():
    payload = {"sections": _complete_sections(), "incomplete_sections": []}
    fenced = "```json\n" + __json_dumps(payload) + "\n```"
    report = parse_evaluation_report(fenced)
    assert report.is_complete is True


def test_parse_evaluation_report_accepts_inference_response():
    payload = {"sections": _complete_sections(), "incomplete_sections": []}
    resp = InferenceResponse(text=__json_dumps(payload), provider="mock")
    report = parse_evaluation_report(resp)
    assert report.is_complete is True


# ---------------------------------------------------------------------------
# Schema: recall match (matched / partial / missed + evidence, P5 anti-gaming)
# ---------------------------------------------------------------------------
def test_parse_recall_match_captures_all_classifications_with_evidence():
    payload = {
        "concepts": [
            {"concept": "a", "classification": "recalled", "evidence": "in my words a"},
            {"concept": "b", "classification": "partial", "evidence": "partly b"},
            {"concept": "c", "classification": "missed", "evidence": ""},
        ]
    }
    result = parse_recall_match(__import_json(payload))
    assert isinstance(result, RecallMatchSchema)
    by_concept = {c.concept: c for c in result.concepts}
    assert by_concept["a"].classification == "recalled"
    assert by_concept["a"].evidence == "in my words a"
    assert by_concept["b"].classification == "partial"
    assert by_concept["c"].classification == "missed"
    assert by_concept["c"].evidence == ""


def test_recall_verbatim_echo_is_forced_to_missed():
    # Anti-gaming (P5 / R14.7): verbatim echo cannot count as recall.
    payload = {
        "concepts": [
            {
                "concept": "a",
                "classification": "recalled",
                "evidence": "exact script text",
                "verbatim_echo": True,
            }
        ]
    }
    result = parse_recall_match(__import_json(payload))
    concept = result.concepts[0]
    assert concept.classification == "missed"
    assert concept.evidence == ""


def test_recall_recalled_without_evidence_is_rejected():
    payload = {
        "concepts": [{"concept": "a", "classification": "recalled", "evidence": ""}]
    }
    with pytest.raises(SchemaValidationError):
        parse_recall_match(__import_json(payload))


def test_recall_rejects_unknown_classification():
    payload = {"concepts": [{"concept": "a", "classification": "perfect", "evidence": "x"}]}
    with pytest.raises(SchemaValidationError):
        parse_recall_match(__import_json(payload))


def test_recall_rejects_empty_concept_list():
    with pytest.raises(SchemaValidationError):
        parse_recall_match(__import_json({"concepts": []}))


def test_recall_rejects_malformed_json():
    with pytest.raises(SchemaValidationError):
        parse_recall_match("{ not json")


# ---------------------------------------------------------------------------
# Schema: hint
# ---------------------------------------------------------------------------
def test_parse_hint_accepts_well_formed_sample():
    payload = {"hint": "What happens at the youthful stage?", "target_concept": "youthful stage"}
    hint = parse_hint(__import_json(payload))
    assert isinstance(hint, HintSchema)
    assert hint.target_concept == "youthful stage"


def test_parse_hint_rejects_missing_field():
    with pytest.raises(SchemaValidationError):
        parse_hint(__import_json({"hint": "cue only"}))


def test_parse_hint_rejects_empty_hint():
    with pytest.raises(SchemaValidationError):
        parse_hint(__import_json({"hint": "  ", "target_concept": "x"}))


# ---------------------------------------------------------------------------
# Direct schema unit checks
# ---------------------------------------------------------------------------
def test_evaluation_section_rejects_out_of_range_score():
    with pytest.raises(Exception):
        EvaluationSection(feedback="ok", score=11.0)


def test_concept_classification_missed_clears_evidence():
    c = ConceptClassification(concept="a", classification="missed", evidence="leftover")
    assert c.evidence == ""


# ---------------------------------------------------------------------------
# GS Geography isolation (Requirement 2 / Property 9)
# ---------------------------------------------------------------------------
def test_prompts_module_does_not_reference_gs_geography():
    import inspect

    mod = importlib.import_module("app.core.optional.prompts")
    source = inspect.getsource(mod)
    assert "/upsc/geography" not in source.lower()


# ---------------------------------------------------------------------------
# Small JSON helpers (kept local so tests document the exact payload shapes)
# ---------------------------------------------------------------------------
def __json_dumps(obj) -> str:
    import json

    return json.dumps(obj)


def __import_json(obj) -> str:
    """Serialize a dict payload to a JSON string for the parsers under test."""
    return __json_dumps(obj)
