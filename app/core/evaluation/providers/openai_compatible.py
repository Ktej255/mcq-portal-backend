"""OpenAI-compatible inference provider for the evaluation core (R3.4, R4.1).

Implements :class:`IInferenceProvider` against any OpenAI-compatible
``/v1/chat/completions`` endpoint identified by ``base_url`` + ``model_id`` +
``api_key_ref``. This single provider reaches the common open-source serving
stacks — **vLLM, Ollama, TGI, SGLang, LM Studio** — so a self-hosted GLM-class
model becomes usable by configuration alone (R3.4).

When ``structured_output_mode == "native"`` it requests JSON-object output via
``response_format`` (R4.1); otherwise it relies on the prompt-instructed JSON
plus downstream repair (R4.2). Vision is supported by attaching the image as a
base64 data URL when the config advertises ``supports_vision`` (R13.1).

Subject-neutral: imports only the core + the existing inference contracts.
"""
from __future__ import annotations

import base64
from typing import Any, Dict, List

from app.core.inference.contracts import (
    IInferenceProvider,
    InferenceRequest,
    InferenceResponse,
)
from app.core.evaluation.providers.config import ConfigurationError, ProviderConfig


class OpenAICompatibleProvider(IInferenceProvider):
    """Talks to an OpenAI-compatible chat-completions endpoint.

    The instance carries its :class:`ProviderConfig` so callers/tests can verify
    config-driven resolution (model id, base URL, API key reference, etc.).
    """

    def __init__(self, config: ProviderConfig) -> None:
        if not config.base_url:
            raise ConfigurationError(
                f"OpenAI-compatible provider '{config.key}' requires a base_url"
            )
        self.config = config
        self.name = config.key

    # -- message assembly ---------------------------------------------------
    def _build_messages(self, request: InferenceRequest) -> List[Dict[str, Any]]:
        messages: List[Dict[str, Any]] = []
        if request.system_instruction:
            messages.append({"role": "system", "content": request.system_instruction})

        if request.image is not None and self.config.supports_vision:
            mime = request.image_mime_type or "image/png"
            b64 = base64.b64encode(request.image).decode("ascii")
            data_url = f"data:{mime};base64,{b64}"
            messages.append(
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": request.prompt},
                        {"type": "image_url", "image_url": {"url": data_url}},
                    ],
                }
            )
        else:
            messages.append({"role": "user", "content": request.prompt})
        return messages

    def _build_payload(self, request: InferenceRequest) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "model": self.config.model_id,
            "messages": self._build_messages(request),
            "temperature": request.temperature,
            "max_tokens": request.max_tokens or self.config.max_tokens,
        }
        # Native structured output (where the server supports it). For "prompt"
        # mode we rely on the prompt + downstream JSON repair (R4.2).
        if (
            self.config.structured_output_mode == "native"
            and (request.response_mime_type or "").endswith("json")
        ):
            payload["response_format"] = {"type": "json_object"}
        return payload

    # -- generation ---------------------------------------------------------
    def generate(self, request: InferenceRequest) -> InferenceResponse:
        try:
            import httpx  # already a project dependency (requirements.txt)
        except Exception as exc:  # pragma: no cover - environment dependent
            raise ConfigurationError(
                "The 'httpx' package is required for the OpenAI-compatible "
                "provider but is not installed."
            ) from exc

        headers = {"Content-Type": "application/json"}
        api_key = self.config.resolve_api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        url = self.config.base_url.rstrip("/") + "/chat/completions"
        response = httpx.post(
            url,
            json=self._build_payload(request),
            headers=headers,
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()

        text = ""
        choices = data.get("choices") or []
        if choices:
            message = choices[0].get("message") or {}
            text = message.get("content") or ""

        usage_raw = data.get("usage") or {}
        usage = {k: int(v) for k, v in usage_raw.items() if isinstance(v, (int, float))}

        return InferenceResponse(
            text=text,
            raw_response=data,
            usage_metadata=usage,
            provider=f"openai-compatible/{self.config.model_id}",
        )

    async def generate_async(self, request: InferenceRequest) -> InferenceResponse:
        # Sync implementation is sufficient for the background-job worker; an
        # async HTTP client can replace this without changing the interface.
        return self.generate(request)


__all__ = ["OpenAICompatibleProvider"]
