"""Re-export shim for the Optional platform's answer-evaluation provider.

The provider abstraction + implementations (mock + gateway) and the env-driven
factory have been MOVED into the shared, subject-neutral evaluation core
(:mod:`app.core.evaluation.providers.evaluation`) so both Optional and GS LMS
reuse one engine (behavior-preserving refactor — Requirement 19).

This module re-exports them so existing imports such as
``from app.core.optional.providers.evaluation import get_evaluation_provider``
keep working unchanged. Nothing here references GS Geography modules
(Requirement 2 / Property 9).
"""
from __future__ import annotations

from app.core.evaluation.providers.evaluation import (  # noqa: F401  (re-export)
    EvaluationProvider,
    GatewayEvaluationProvider,
    MockEvaluationProvider,
    _all_incomplete,
    get_evaluation_provider,
)

__all__ = [
    "EvaluationProvider",
    "MockEvaluationProvider",
    "GatewayEvaluationProvider",
    "get_evaluation_provider",
]
