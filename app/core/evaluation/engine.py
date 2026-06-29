"""Subject-neutral evaluation engine (R1.1, R1.3, R1.4, R1.5).

The single entry point that turns a student's answer + an injected rubric
strategy into an assembled :class:`EvaluationReport`. It never imports a domain
to decide behavior — the variation is supplied by the :class:`RubricStrategy`
(R1.4). It resolves the model "brain" through the config-driven
:class:`ProviderRegistry` (so a self-hosted OSS model is a config swap — R3), runs
the call through the resilience guard with a unified retry loop (R4.4, R5),
repairs/validates the model JSON (R4.2/R4.3), degrades honestly to an
all-incomplete report on terminal failure (R4.5/R5.5, Property 1/3), and applies
marks- and length-normalized, reference-grounded scoring (R7, R8). Identical
report SHAPE regardless of strategy or provider (R1.5).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from app.core.evaluation.cache import ReportCache, content_hash
from app.core.evaluation.json_io import JsonRepair
from app.core.evaluation.prompts import build_evaluation_request, parse_evaluation_report
from app.core.evaluation.providers.evaluation import _all_incomplete
from app.core.evaluation.providers.registry import ProviderRegistry, get_default_registry
from app.core.evaluation.resilience import (
    CircuitOpenError,
    guarded_call,
    is_retriable,
    record_failure,
)
from app.core.evaluation.rubric import RubricStrategy
from app.core.evaluation.schema import (
    EvaluationReport,
    EvaluationReportSchema,
    MarkingScheme,
    SchemaValidationError,
)
from app.core.evaluation.scoring import (
    count_words,
    length_adjustment_factor,
    normalize_marks,
)


@dataclass
class EvaluationInput:
    """Subject-neutral input to :meth:`EvaluationEngine.evaluate` (R1.1)."""

    answer_text: str
    rubric_strategy: RubricStrategy
    marking_scheme: MarkingScheme = field(default_factory=MarkingScheme)
    question: Optional[str] = None
    reference_answer: Optional[str] = None
    answer_images: List[bytes] = field(default_factory=list)
    provider_key: Optional[str] = None


class EvaluationEngine:
    """Orchestrates one evaluation end-to-end (subject-neutral)."""

    # Backoff base seconds between retries; 0.0 keeps tests fast. Production can
    # raise this via subclass/attribute for gentler retry pacing.
    backoff_base: float = 0.0

    def __init__(
        self,
        registry: Optional[ProviderRegistry] = None,
        cache: Optional[ReportCache] = None,
    ) -> None:
        self._registry = registry or get_default_registry()
        self._cache = cache

    def evaluate(self, request: EvaluationInput) -> EvaluationReport:
        strategy = request.rubric_strategy
        required_sections = tuple(strategy.required_sections())
        rubric = strategy.build_rubric(
            question=request.question,
            reference_answer=request.reference_answer,
            marking_scheme=request.marking_scheme,
        )

        # Cache check (R18.1 / Property 21).
        cache_key = content_hash(
            answer_text=request.answer_text,
            question=request.question,
            rubric=rubric,
            required_sections=required_sections,
        )
        if self._cache is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        config = self._registry.resolve_config(request.provider_key)
        schema = self._run_with_retries(request, rubric, required_sections)

        report = self._assemble_report(
            schema=schema,
            request=request,
            strategy=strategy,
            provider_key=config.key,
        )

        if self._cache is not None and report.is_complete:
            self._cache.put(cache_key, report)
        return report

    # -- internals ----------------------------------------------------------
    def _run_with_retries(
        self,
        request: EvaluationInput,
        rubric: str,
        required_sections: tuple,
    ) -> EvaluationReportSchema:
        """Unified retry loop spanning transient + unparseable-JSON failures.

        Issues exactly ``retry_limit + 1`` inference attempts in the worst case
        (Property 4), degrading to an all-incomplete report on terminal failure
        (Property 3).
        """
        import time

        config = self._registry.resolve_config(request.provider_key)
        provider = self._registry.resolve(request.provider_key)

        inf_request = build_evaluation_request(
            request.answer_text,
            rubric,
            required_sections=required_sections,
            question=request.question,
        )
        inf_request.max_tokens = config.max_tokens  # token budget per call (R18.3)

        # Vision route: attach the first page image when the model supports it
        # so diagrams/maps are graded directly (R13.1).
        from app.core.evaluation.providers.vision import apply_vision

        apply_vision(inf_request, request.answer_images, config)

        attempts = config.retry_limit + 1
        for attempt in range(attempts):
            try:
                response = guarded_call(provider, inf_request, config)
            except CircuitOpenError:
                # Breaker open — terminal, no point retrying (Property 3).
                return _all_incomplete(required_sections)
            except Exception as exc:  # noqa: BLE001 - classified
                record_failure(config)
                if is_retriable(exc) and attempt < attempts - 1:
                    if self.backoff_base:
                        time.sleep(self.backoff_base * (2 ** attempt))
                    continue
                return _all_incomplete(required_sections)

            # Parse + repair the model output.
            try:
                return parse_evaluation_report(response)
            except SchemaValidationError:
                repaired = JsonRepair.extract_object(getattr(response, "text", "") or "")
                if repaired is not None:
                    try:
                        return EvaluationReportSchema(**repaired)
                    except Exception:  # noqa: BLE001 - invalid repaired payload
                        pass
                # Unparseable on this attempt — count and retry if budget remains.
                record_failure(config)
                if attempt < attempts - 1:
                    if self.backoff_base:
                        time.sleep(self.backoff_base * (2 ** attempt))
                    continue
                return _all_incomplete(required_sections)

        return _all_incomplete(required_sections)

    def _assemble_report(
        self,
        *,
        schema: EvaluationReportSchema,
        request: EvaluationInput,
        strategy: RubricStrategy,
        provider_key: str,
    ) -> EvaluationReport:
        """Assemble the rich report: marks/length normalization + bookkeeping."""
        marking = request.marking_scheme
        word_count = count_words(request.answer_text)
        word_limit = strategy.word_limit(marking)
        factor = length_adjustment_factor(word_count, word_limit)
        marks_awarded = normalize_marks(
            schema.overall_score, marking.max_marks, length_factor=factor
        )

        # Value-addition assessment reflects diagrams/maps when the model
        # produced that section (R13.3). Absent visuals are not penalized.
        value_addition = None
        va_section = schema.sections.get("value_addition")
        if va_section is not None:
            value_addition = {"assessment": va_section.feedback, "score": va_section.score}

        return EvaluationReport(
            sections=schema.sections,
            incomplete_sections=schema.incomplete_sections,
            overall_score=schema.overall_score,
            marks_awarded=marks_awarded,
            max_marks=marking.max_marks,
            word_count=word_count,
            word_limit=word_limit,
            factual_accuracy=None,
            value_addition=value_addition,
            provider_key=provider_key,
            token_usage=None,
        )


__all__ = ["EvaluationEngine", "EvaluationInput"]
