"""Answer-evaluation provider abstraction for the shared evaluation core.

Moved verbatim (behavior-preserving) from
``app.core.optional.providers.evaluation`` (R19.1/R19.2). Mirrors the
inference-gateway pattern (interface + concrete impl + deterministic mock +
env-driven selector). Callers depend on the :class:`EvaluationProvider`
interface only, so the concrete backend can be swapped without touching the
answer-writing pipeline.

Honesty (design **Property 6**): a report is "complete" only when no required
section is missing; if the model cannot produce a section it is named in
``incomplete_sections`` rather than fabricated. Total model/parse failure
degrades honestly to an *all-incomplete* report — never a fabricated complete
one.

Subject-neutral: references no GS or Optional modules (Requirement 2 /
Property 9).
"""
from __future__ import annotations

import os
from abc import ABC, abstractmethod
from typing import Optional, Sequence

from app.core.inference.contracts import (
    IInferenceProvider,
    InferenceRequest,
    InferenceResponse,
)
from app.core.evaluation.prompts import (
    build_evaluation_request,
    parse_evaluation_report,
)
from app.core.evaluation.schema import (
    REQUIRED_EVALUATION_SECTIONS,
    EvaluationReportSchema,
    EvaluationSection,
    SchemaValidationError,
)


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
class EvaluationProvider(ABC):
    """Abstract answer-evaluation provider.

    Implementations turn a student's answer + rubric into a schema-valid
    :class:`EvaluationReportSchema`. The returned report always accounts for
    every required section (produced in ``sections`` OR named in
    ``incomplete_sections``) — never fabricated, never silently dropped
    (design Property 6 / R6).
    """

    name: str = "abstract"

    @abstractmethod
    def evaluate(
        self,
        *,
        answer_text: str,
        rubric: str,
        question: Optional[str] = None,
        required_sections: Sequence[str] = REQUIRED_EVALUATION_SECTIONS,
    ) -> EvaluationReportSchema:
        """Evaluate ``answer_text`` and return a schema-valid report."""
        raise NotImplementedError


def _all_incomplete(required_sections: Sequence[str]) -> EvaluationReportSchema:
    """Honest degradation: a report with EVERY required section flagged missing.

    Used when the model/parse step fails entirely. This is schema-valid (every
    required section is accounted for, all in ``incomplete_sections``) and is
    explicitly NOT "complete" (``is_complete`` is False), so the UI surfaces an
    honest "could not be produced" report rather than a fabricated one
    (design Property 6 / R6).
    """
    return EvaluationReportSchema(
        sections={},
        incomplete_sections=list(required_sections),
        overall_score=None,
    )


# ---------------------------------------------------------------------------
# Deterministic mock implementation
# ---------------------------------------------------------------------------
class MockEvaluationProvider(EvaluationProvider):
    """Deterministic, dependency-free evaluator for tests and local/dev.

    Mirrors ``inference.mock_provider.MockProvider`` and the sibling STT/OCR
    mocks: no network, no model. Produces a **complete** schema-valid report
    (every required section present) so the end-to-end answer → report flow is
    demoable offline. The per-section feedback and scores are derived
    deterministically from the answer so the same answer always yields the same
    report (useful for stable tests), and they reference the answer length so
    the output is plausibly answer-specific rather than constant.
    """

    name = "mock"

    def evaluate(
        self,
        *,
        answer_text: str,
        rubric: str,
        question: Optional[str] = None,
        required_sections: Sequence[str] = REQUIRED_EVALUATION_SECTIONS,
    ) -> EvaluationReportSchema:
        word_count = len(answer_text.split())
        # Deterministic per-section score in [4, 9] keyed off the section name +
        # answer size, so it varies plausibly yet reproducibly.
        sections: dict[str, EvaluationSection] = {}
        score_total = 0.0
        for idx, name in enumerate(required_sections):
            score = 4.0 + float((word_count + idx * 3) % 6)  # 4.0 .. 9.0
            score_total += score
            sections[name] = EvaluationSection(
                feedback=(
                    f"[Mock evaluation] Assessment of '{name}' for a "
                    f"{word_count}-word answer. This deterministic evaluator "
                    "produces a complete report so the answer→report flow is "
                    "demoable offline; a configured Gemini backend replaces it "
                    "in production."
                ),
                score=score,
            )
        # Overall score normalised to 0..100 from the per-section average.
        overall = round((score_total / max(len(required_sections), 1)) * 10.0, 1)
        return EvaluationReportSchema(
            sections=sections,
            incomplete_sections=[],
            overall_score=min(100.0, overall),
        )


# ---------------------------------------------------------------------------
# Gateway (Gemini) implementation — via the existing inference gateway
# ---------------------------------------------------------------------------
class GatewayEvaluationProvider(EvaluationProvider):
    """Evaluator routed through the EXISTING inference gateway (Gemini).

    The production integration seam. Builds the strict-JSON evaluation request
    with :func:`app.core.evaluation.prompts.build_evaluation_request` (LOW
    temperature), sends it through the gateway, and validates the response with
    :func:`parse_evaluation_report`. The gateway is imported **lazily** so
    importing this module never requires the gateway/credentials.

    Honesty (design Property 6 / R6): if the gateway call fails (no creds /
    backend down) or the model returns output that fails strict validation, the
    provider degrades to an *all-incomplete* report rather than trusting bad
    output or fabricating a "complete" one.
    """

    name = "gemini"

    def __init__(self, provider_name: str = "gemini"):
        # Which gateway provider to route through (the real Gemini provider by
        # default; tests/dev can point the gateway at its own mock).
        self.provider_name = provider_name

    def evaluate(
        self,
        *,
        answer_text: str,
        rubric: str,
        question: Optional[str] = None,
        required_sections: Sequence[str] = REQUIRED_EVALUATION_SECTIONS,
    ) -> EvaluationReportSchema:
        request = build_evaluation_request(
            answer_text,
            rubric,
            required_sections=required_sections,
            question=question,
        )

        try:
            from app.core.inference.gateway import InferenceGateway

            response = InferenceGateway.get_provider(self.provider_name).generate(request)
        except Exception:
            # Backend not operational in this environment — honest degradation
            # (never a fabricated complete report).
            return _all_incomplete(required_sections)

        try:
            return parse_evaluation_report(response)
        except SchemaValidationError:
            # Model returned malformed / non-conforming output — flag everything
            # as incomplete rather than trusting it (Property 6 / R6).
            return _all_incomplete(required_sections)


# ---------------------------------------------------------------------------
# Selector / factory (env-driven, like the inference gateway)
# ---------------------------------------------------------------------------
_PROVIDERS: dict = {}


def get_evaluation_provider(name: Optional[str] = None) -> EvaluationProvider:
    """Return an :class:`EvaluationProvider`, selected by ``name`` or environment.

    Selection precedence:
        1. explicit ``name`` argument
        2. ``OPTIONAL_EVAL_PROVIDER`` environment variable
        3. default → ``"mock"``

    The mock is the safe default for test/dev (no model, deterministic complete
    report), exactly like the inference gateway and the STT/OCR selectors.
    Providers are cached per-name. ``ValueError`` is raised for unknown names.
    """
    resolved = (
        name or os.environ.get("OPTIONAL_EVAL_PROVIDER") or "mock"
    ).strip().lower()

    if resolved in _PROVIDERS:
        return _PROVIDERS[resolved]

    if resolved == "mock":
        provider: EvaluationProvider = MockEvaluationProvider()
    elif resolved in ("gemini", "gateway"):
        provider = GatewayEvaluationProvider()
    else:
        raise ValueError(f"Unknown evaluation provider '{resolved}'")

    _PROVIDERS[resolved] = provider
    return provider


__all__ = [
    "EvaluationProvider",
    "MockEvaluationProvider",
    "GatewayEvaluationProvider",
    "MockEvaluationInferenceProvider",
    "get_evaluation_provider",
    "_all_incomplete",
]


# ---------------------------------------------------------------------------
# Evaluation-aware mock INFERENCE provider (for the registry/engine path)
# ---------------------------------------------------------------------------
class MockEvaluationInferenceProvider(IInferenceProvider):
    """A deterministic :class:`IInferenceProvider` that returns a COMPLETE
    evaluation report as JSON text.

    The :class:`EvaluationEngine` resolves providers at the inference level
    (``generate(request) -> InferenceResponse``) and then parses the response
    text as a strict evaluation report. The generic inference mock returns plain
    prose, which would (correctly) degrade to all-incomplete; this mock instead
    returns a schema-valid complete report so the engine's offline/dev path
    mirrors the old :class:`MockEvaluationProvider` behavior (complete report,
    no network).
    """

    name = "mock"

    def generate(self, request: InferenceRequest) -> InferenceResponse:
        sections = {
            name: EvaluationSection(
                feedback=(
                    f"[Mock evaluation] Deterministic assessment of '{name}'. "
                    "A configured model replaces this in production."
                ),
                score=7.0,
            )
            for name in REQUIRED_EVALUATION_SECTIONS
        }
        report = EvaluationReportSchema(
            sections=sections, incomplete_sections=[], overall_score=70.0
        )
        return InferenceResponse(
            text=report.model_dump_json(),
            usage_metadata={"total_tokens": 0},
            provider="mock/eval",
        )

    async def generate_async(self, request: InferenceRequest) -> InferenceResponse:
        return self.generate(request)
