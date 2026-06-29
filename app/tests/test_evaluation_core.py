"""Tests for the shared, model-agnostic evaluation core.

Covers the subject-neutral engine, provider registry, JSON repair, resilience,
and marks/length-normalized scoring. Property-based tests (Hypothesis, >=100
iterations) verify the universal invariants from the design.

Feature: unified-answer-evaluation-engine
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from app.core.inference.contracts import IInferenceProvider, InferenceRequest, InferenceResponse
from app.core.evaluation.engine import EvaluationEngine, EvaluationInput
from app.core.evaluation.json_io import JsonRepair
from app.core.evaluation.providers.config import ConfigurationError, ProviderConfig
from app.core.evaluation.providers.registry import ProviderRegistry
from app.core.evaluation.resilience import reset_breakers
from app.core.evaluation.rubric import PrebuiltRubricStrategy
from app.core.evaluation.schema import (
    REQUIRED_EVALUATION_SECTIONS,
    EvaluationReportSchema,
    EvaluationSection,
    MarkingScheme,
)
from app.core.evaluation.scoring import length_adjustment_factor, normalize_marks
from app.core.gs_lms.evaluation.rubric import GsPaperRubricStrategy


# ---------------------------------------------------------------------------
# Test inference providers
# ---------------------------------------------------------------------------
def _complete_report_json(score: float = 70.0) -> str:
    rep = EvaluationReportSchema(
        sections={
            n: EvaluationSection(feedback=f"fb {n}", score=7.0)
            for n in REQUIRED_EVALUATION_SECTIONS
        },
        incomplete_sections=[],
        overall_score=score,
    )
    return rep.model_dump_json()


class _CompleteProvider(IInferenceProvider):
    def generate(self, request):
        return InferenceResponse(text=_complete_report_json(), provider="t/complete")

    async def generate_async(self, request):
        return self.generate(request)


class _CountingFailProvider(IInferenceProvider):
    """Raises a retriable error on every call, counting attempts."""

    def __init__(self):
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        raise TimeoutError("simulated transient failure")

    async def generate_async(self, request):
        return self.generate(request)


class _CountingBadJsonProvider(IInferenceProvider):
    """Returns unparseable text on every call, counting attempts."""

    def __init__(self):
        self.calls = 0

    def generate(self, request):
        self.calls += 1
        return InferenceResponse(text="this is not json at all", provider="t/bad")

    async def generate_async(self, request):
        return self.generate(request)


def _registry_with(provider: IInferenceProvider) -> ProviderRegistry:
    reg = ProviderRegistry()
    reg.register("mock", lambda _cfg: provider)  # mock built-in config: retry_limit=2
    return reg


# ---------------------------------------------------------------------------
# Property 1: Report-completeness honesty
# ---------------------------------------------------------------------------
# Feature: unified-answer-evaluation-engine, Property 1: report-completeness honesty
@settings(max_examples=100, deadline=None)
@given(
    produced=st.lists(
        st.sampled_from(list(REQUIRED_EVALUATION_SECTIONS)), unique=True
    )
)
def test_property1_report_completeness_honesty(produced):
    incomplete = [s for s in REQUIRED_EVALUATION_SECTIONS if s not in produced]
    schema = EvaluationReportSchema(
        sections={s: EvaluationSection(feedback="x", score=5.0) for s in produced},
        incomplete_sections=incomplete,
    )
    # Every required section accounted for exactly once.
    accounted = set(schema.sections) | set(schema.incomplete_sections)
    assert accounted == set(REQUIRED_EVALUATION_SECTIONS)
    assert not (set(schema.sections) & set(schema.incomplete_sections))
    assert schema.is_complete == (len(schema.incomplete_sections) == 0)


def test_property1_empty_feedback_is_not_a_produced_section():
    import pytest

    with pytest.raises(Exception):
        EvaluationSection(feedback="   ")


# ---------------------------------------------------------------------------
# Property 2: Report-shape invariance across strategy
# ---------------------------------------------------------------------------
def test_property2_shape_invariance_across_strategies():
    eng = EvaluationEngine(_registry_with(_CompleteProvider()))
    opt = eng.evaluate(
        EvaluationInput(
            answer_text="ans " * 30,
            rubric_strategy=PrebuiltRubricStrategy("r"),
            provider_key="mock",
        )
    )
    gs = eng.evaluate(
        EvaluationInput(
            answer_text="ans " * 30,
            rubric_strategy=GsPaperRubricStrategy("GS1"),
            marking_scheme=MarkingScheme(max_marks=15),
            provider_key="mock",
        )
    )
    assert set(opt.sections) == set(gs.sections) == set(REQUIRED_EVALUATION_SECTIONS)
    assert opt.model_fields.keys() == gs.model_fields.keys()


# ---------------------------------------------------------------------------
# Property 3 + 4: honest degradation + retry up to the configured limit
# ---------------------------------------------------------------------------
# Feature: unified-answer-evaluation-engine, Property 4: retry up to the configured limit
@settings(max_examples=100, deadline=None)
@given(seed=st.integers(min_value=0, max_value=1000))
def test_property4_retries_transient_up_to_limit(seed):
    reset_breakers()
    prov = _CountingFailProvider()
    eng = EvaluationEngine(_registry_with(prov))
    report = eng.evaluate(
        EvaluationInput(
            answer_text="ans", rubric_strategy=PrebuiltRubricStrategy("r"), provider_key="mock"
        )
    )
    # mock built-in retry_limit=2 → exactly 3 attempts; then honest degradation.
    assert prov.calls == 3
    assert not report.is_complete
    assert set(report.incomplete_sections) == set(REQUIRED_EVALUATION_SECTIONS)


# Feature: unified-answer-evaluation-engine, Property 4: retry up to the configured limit
@settings(max_examples=100, deadline=None)
@given(seed=st.integers(min_value=0, max_value=1000))
def test_property4_retries_badjson_up_to_limit(seed):
    reset_breakers()
    prov = _CountingBadJsonProvider()
    eng = EvaluationEngine(_registry_with(prov))
    report = eng.evaluate(
        EvaluationInput(
            answer_text="ans", rubric_strategy=PrebuiltRubricStrategy("r"), provider_key="mock"
        )
    )
    assert prov.calls == 3
    assert not report.is_complete  # Property 3: degraded, never fabricated


# ---------------------------------------------------------------------------
# Property 5: JSON repair recovers embedded objects
# ---------------------------------------------------------------------------
# Feature: unified-answer-evaluation-engine, Property 5: JSON repair recovers embedded objects
@settings(max_examples=100, deadline=None)
@given(
    pre=st.text(alphabet=st.characters(blacklist_characters="{}"), max_size=40),
    post=st.text(alphabet=st.characters(blacklist_characters="{}"), max_size=40),
    val=st.integers(),
)
def test_property5_json_repair(pre, post, val):
    raw = f'{pre}```json\n{{"a": {val}, "b": "x"}}\n```{post}'
    obj = JsonRepair.extract_object(raw)
    assert obj == {"a": val, "b": "x"}


def test_property5_json_repair_returns_none_for_no_object():
    assert JsonRepair.extract_object("no json here") is None
    assert JsonRepair.extract_object("") is None


# ---------------------------------------------------------------------------
# Property 6 + 7: config-driven resolution / swap invariance + config errors
# ---------------------------------------------------------------------------
def test_property6_provider_swap_via_config(monkeypatch):
    # Two OSS-style keys configured purely via env.
    for key, model in [("glm", "glm-4.5"), ("qwen", "qwen2.5")]:
        up = key.upper()
        monkeypatch.setenv(f"EVAL_PROVIDER_{up}_MODEL_ID", model)
        monkeypatch.setenv(f"EVAL_PROVIDER_{up}_BASE_URL", f"http://localhost/{key}/v1")
    reg = ProviderRegistry()
    glm = reg.resolve("glm")
    qwen = reg.resolve("qwen")
    assert glm.config.model_id == "glm-4.5"
    assert qwen.config.model_id == "qwen2.5"
    assert glm.config.base_url.endswith("/glm/v1")
    # No name branching: resolving by changing the key yields the new provider.
    assert glm is not qwen


def test_property7_config_errors_name_the_key():
    import pytest

    reg = ProviderRegistry()
    with pytest.raises(ConfigurationError) as ei:
        reg.resolve("does-not-exist")
    assert "does-not-exist" in str(ei.value)


# ---------------------------------------------------------------------------
# Property 8: marks-normalized score bounds
# ---------------------------------------------------------------------------
# Feature: unified-answer-evaluation-engine, Property 8: marks-normalized score bounds
@settings(max_examples=100, deadline=None)
@given(
    overall=st.floats(min_value=-500, max_value=500, allow_nan=False, allow_infinity=False),
    max_marks=st.integers(min_value=1, max_value=50),
    factor=st.floats(min_value=-2.0, max_value=2.0, allow_nan=False),
)
def test_property8_marks_bounds(overall, max_marks, factor):
    marks = normalize_marks(overall, max_marks, length_factor=factor)
    assert marks is not None
    assert 0.0 <= marks <= float(max_marks)


def test_property8_marks_none_without_max():
    assert normalize_marks(70.0, None) is None


# ---------------------------------------------------------------------------
# Property 11 + 12: word-limit derivation + length monotonicity
# ---------------------------------------------------------------------------
# Feature: unified-answer-evaluation-engine, Property 11: word-limit derivation
@settings(max_examples=100, deadline=None)
@given(max_marks=st.integers(min_value=1, max_value=40))
def test_property11_word_limit_buckets(max_marks):
    wl = GsPaperRubricStrategy("GS3").word_limit(MarkingScheme(max_marks=max_marks))
    assert wl == (150 if max_marks <= 12 else 250)


# Feature: unified-answer-evaluation-engine, Property 12: length-normalization monotonicity
@settings(max_examples=100, deadline=None)
@given(
    word_limit=st.integers(min_value=10, max_value=300),
    base=st.integers(min_value=0, max_value=400),
    extra=st.integers(min_value=0, max_value=400),
)
def test_property12_length_factor_non_increasing(word_limit, base, extra):
    wc1 = word_limit + base
    wc2 = wc1 + extra
    f1 = length_adjustment_factor(wc1, word_limit)
    f2 = length_adjustment_factor(wc2, word_limit)
    # Beyond the limit, more words never increases the factor.
    assert f2 <= f1 + 1e-9


# ---------------------------------------------------------------------------
# Property 13: GS rubric reflects its paper
# ---------------------------------------------------------------------------
def test_property13_gs_rubric_reflects_paper():
    ms = MarkingScheme(max_marks=15)
    for paper, marker in [("GS1", "Paper I"), ("GS2", "Paper II"), ("GS3", "Paper III"), ("GS4", "Paper IV")]:
        rubric = GsPaperRubricStrategy(paper).build_rubric(
            question="q", reference_answer=None, marking_scheme=ms
        )
        assert marker in rubric


# ---------------------------------------------------------------------------
# Property 10: reference grounding without fabrication
# ---------------------------------------------------------------------------
def test_property10_reference_grounding():
    ms = MarkingScheme(max_marks=15)
    with_ref = GsPaperRubricStrategy("GS1").build_rubric(
        question="q", reference_answer="MODEL POINTS", marking_scheme=ms
    )
    without_ref = GsPaperRubricStrategy("GS1").build_rubric(
        question="q", reference_answer=None, marking_scheme=ms
    )
    assert "MODEL POINTS" in with_ref
    assert "do NOT fabricate" in without_ref
