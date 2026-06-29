"""Provider configuration for the model-agnostic evaluation core (R3).

A :class:`ProviderConfig` fully describes how to reach a model "brain" — model
id, endpoint base URL, the NAME of the secret holding its API key (never the
secret value itself), token/timeout/retry budgets, and whether it speaks native
structured output. Swapping the production model (e.g. to a self-hosted
GLM-class model served via vLLM/Ollama/TGI behind an OpenAI-compatible endpoint)
is therefore a CONFIG change, not a code change (R3.4).

Configs are sourced from environment variables so deployment can repoint the
active model without code edits. Nothing here imports a domain (Requirement 2).
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Dict, Literal, Optional

StructuredOutputMode = Literal["native", "prompt"]


class ConfigurationError(RuntimeError):
    """Raised when a provider key or required config value cannot be resolved.

    The message always names the offending key or value so misconfiguration is
    actionable rather than silent (R3.5, R3.6).
    """


@dataclass(frozen=True)
class ProviderConfig:
    """Immutable description of one model backend (R3.2).

    ``api_key_ref`` is the NAME of the environment variable / secret that holds
    the key, not the key itself, so secrets never live in config objects or logs
    (R17.5).
    """

    key: str
    model_id: str
    base_url: Optional[str] = None
    api_key_ref: Optional[str] = None
    max_tokens: int = 4096
    timeout_seconds: float = 60.0
    retry_limit: int = 2
    structured_output_mode: StructuredOutputMode = "prompt"
    supports_vision: bool = False
    # Consecutive-failure threshold that trips the circuit breaker (R5.4).
    breaker_threshold: int = 5

    def resolve_api_key(self) -> Optional[str]:
        """Resolve the actual API key from the referenced env var (if any)."""
        if not self.api_key_ref:
            return None
        return os.environ.get(self.api_key_ref)


# ---------------------------------------------------------------------------
# Environment-driven config loading
# ---------------------------------------------------------------------------
# Built-in defaults always available without any env configuration.
_BUILTIN_CONFIGS: Dict[str, ProviderConfig] = {
    "mock": ProviderConfig(key="mock", model_id="mock", structured_output_mode="prompt"),
    "gemini": ProviderConfig(
        key="gemini",
        model_id=os.environ.get("GEMINI_MODEL_ID", "gemini-1.5-flash"),
        api_key_ref="GEMINI_API_KEY",
        structured_output_mode="native",
        supports_vision=True,
    ),
}


def active_provider_key() -> str:
    """The provider key the engine uses by default (R3.1).

    Resolution: ``EVALUATION_PROVIDER`` env var, else ``OPTIONAL_EVAL_PROVIDER``
    (legacy), else ``"mock"``. Swapping models in production is just changing
    this value (R3.4).
    """
    return (
        os.environ.get("EVALUATION_PROVIDER")
        or os.environ.get("OPTIONAL_EVAL_PROVIDER")
        or "mock"
    ).strip().lower()


def load_provider_config(key: str) -> ProviderConfig:
    """Load a :class:`ProviderConfig` for ``key`` from env, with built-ins.

    An OpenAI-compatible OSS model is configured purely by environment, e.g.::

        EVALUATION_PROVIDER=glm
        EVAL_PROVIDER_GLM_MODEL_ID=glm-4.5
        EVAL_PROVIDER_GLM_BASE_URL=http://localhost:8000/v1
        EVAL_PROVIDER_GLM_API_KEY_REF=GLM_API_KEY
        EVAL_PROVIDER_GLM_STRUCTURED_OUTPUT=native   # or "prompt"
        EVAL_PROVIDER_GLM_SUPPORTS_VISION=true

    Raises :class:`ConfigurationError` naming the missing value when an
    env-declared provider omits a required field (R3.6).
    """
    key = key.strip().lower()
    prefix = f"EVAL_PROVIDER_{key.upper().replace('-', '_')}_"

    model_id = os.environ.get(prefix + "MODEL_ID")
    if model_id is None:
        # Fall back to a built-in config when no env override exists.
        if key in _BUILTIN_CONFIGS:
            return _BUILTIN_CONFIGS[key]
        raise ConfigurationError(
            f"No configuration for evaluation provider '{key}': set "
            f"{prefix}MODEL_ID (and BASE_URL/API_KEY_REF) or use a built-in "
            f"provider key ({', '.join(sorted(_BUILTIN_CONFIGS))})."
        )

    base_url = os.environ.get(prefix + "BASE_URL")
    structured = (os.environ.get(prefix + "STRUCTURED_OUTPUT") or "prompt").strip().lower()
    if structured not in ("native", "prompt"):
        raise ConfigurationError(
            f"{prefix}STRUCTURED_OUTPUT must be 'native' or 'prompt', got {structured!r}"
        )

    def _int(name: str, default: int) -> int:
        raw = os.environ.get(prefix + name)
        return int(raw) if raw not in (None, "") else default

    def _float(name: str, default: float) -> float:
        raw = os.environ.get(prefix + name)
        return float(raw) if raw not in (None, "") else default

    def _bool(name: str, default: bool) -> bool:
        raw = os.environ.get(prefix + name)
        if raw in (None, ""):
            return default
        return raw.strip().lower() in ("1", "true", "yes", "on")

    return ProviderConfig(
        key=key,
        model_id=model_id,
        base_url=base_url,
        api_key_ref=os.environ.get(prefix + "API_KEY_REF"),
        max_tokens=_int("MAX_TOKENS", 4096),
        timeout_seconds=_float("TIMEOUT_SECONDS", 60.0),
        retry_limit=_int("RETRY_LIMIT", 2),
        structured_output_mode=structured,  # type: ignore[arg-type]
        supports_vision=_bool("SUPPORTS_VISION", False),
        breaker_threshold=_int("BREAKER_THRESHOLD", 5),
    )


__all__ = [
    "ProviderConfig",
    "ConfigurationError",
    "StructuredOutputMode",
    "active_provider_key",
    "load_provider_config",
]
