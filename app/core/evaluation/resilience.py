"""Resilient model-call primitives for the evaluation core (R5).

Provides a single-attempt *guarded* call that enforces a hard timeout and
maintains a per-provider circuit breaker. The retry loop itself lives in the
:class:`~app.core.evaluation.engine.EvaluationEngine` so that a single attempt
counter spans BOTH transient provider failures and unparseable-JSON outputs
(design Property 4). Self-hosted OSS endpoints fail transiently more than managed
APIs, so terminal failures here become an honest all-incomplete report upstream —
never a fabricated complete one.

PII protection (R17.5): this layer logs/raises with the provider key, status and
timing only — never answer text, image bytes, or prompt content.

Subject-neutral. Pure orchestration over an injected provider.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
from dataclasses import dataclass
from typing import Dict

from app.core.inference.contracts import (
    IInferenceProvider,
    InferenceRequest,
    InferenceResponse,
)
from app.core.evaluation.providers.config import ProviderConfig


class ResilientCallError(RuntimeError):
    """A single guarded call failed (timeout or provider error).

    Carries only non-sensitive context (provider key + reason).
    """


class CircuitOpenError(ResilientCallError):
    """Raised when the per-provider circuit breaker is open (R5.4)."""


@dataclass
class _BreakerState:
    consecutive_failures: int = 0
    open: bool = False


# Module-level breaker state, keyed by provider key. Survives across calls so a
# string of failures trips the breaker for subsequent calls (R5.4).
_BREAKERS: Dict[str, _BreakerState] = {}


def _breaker(key: str) -> _BreakerState:
    return _BREAKERS.setdefault(key, _BreakerState())


def reset_breakers() -> None:
    """Clear all circuit-breaker state (test helper / manual recovery)."""
    _BREAKERS.clear()


def breaker_is_open(key: str) -> bool:
    """Whether the breaker for ``key`` is currently open."""
    return _breaker(key).open


# Shared executor for enforcing hard timeouts on blocking provider calls.
_EXECUTOR = ThreadPoolExecutor(max_workers=8, thread_name_prefix="eval-call")


def is_retriable(exc: Exception) -> bool:
    """Treat timeouts and transient network/5xx errors as retriable (R5.3).

    A guarded-call timeout surfaces as :class:`ResilientCallError` (retriable),
    while an open circuit surfaces as :class:`CircuitOpenError` (terminal).
    """
    if isinstance(exc, CircuitOpenError):
        return False
    if isinstance(exc, (ResilientCallError, FutureTimeout, TimeoutError)):
        return True
    name = type(exc).__name__.lower()
    if "timeout" in name or "connection" in name:
        return True
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if isinstance(status, int) and status >= 500:
        return True
    return False


def record_failure(config: ProviderConfig) -> None:
    """Count a failed attempt toward the breaker, tripping it at threshold."""
    state = _breaker(config.key)
    state.consecutive_failures += 1
    if state.consecutive_failures >= config.breaker_threshold:
        state.open = True


def guarded_call(
    provider: IInferenceProvider,
    request: InferenceRequest,
    config: ProviderConfig,
) -> InferenceResponse:
    """Run ONE provider call with a hard timeout + breaker guard (R5.1/R5.2/R5.4).

    Raises :class:`CircuitOpenError` immediately when the breaker is open; raises
    :class:`ResilientCallError` (or the underlying exception) on timeout/failure.
    On success the breaker resets. Does NOT retry — the engine owns the loop.
    """
    state = _breaker(config.key)
    if state.open:
        raise CircuitOpenError(
            f"circuit open for provider '{config.key}'; short-circuiting"
        )

    future = _EXECUTOR.submit(provider.generate, request)
    try:
        response = future.result(timeout=config.timeout_seconds)
    except FutureTimeout as exc:
        raise ResilientCallError(
            f"provider '{config.key}' timed out after {config.timeout_seconds}s"
        ) from exc
    # Success — reset failure tracking.
    state.consecutive_failures = 0
    state.open = False
    return response


__all__ = [
    "guarded_call",
    "record_failure",
    "is_retriable",
    "breaker_is_open",
    "reset_breakers",
    "ResilientCallError",
    "CircuitOpenError",
]
