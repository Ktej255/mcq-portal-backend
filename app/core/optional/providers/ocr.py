"""Handwriting OCR provider abstraction for the Optional platform.

Mirrors the inference-gateway pattern (interface + concrete impl + deterministic
mock + env-driven selector) used in ``app/core/inference`` and the sibling
:mod:`app.core.optional.providers.stt`. Callers depend on the
:class:`OcrProvider` interface only, so the concrete backend can be swapped
without touching the answer-writing / upload pipelines (R9.1, R20.1).

Design decision (design.md — "Handwriting OCR"):
    The production implementation is **Gemini Vision via the existing inference
    gateway** (``app/core/inference``). Vision-capable LLMs lead handwriting
    accuracy and Gemini is already integrated, so this reuses the gateway rather
    than adding a new SDK / dependency. A low-confidence result must trigger a
    manual correction / re-upload fallback in the UI — never a silent bad
    transcript (R20.1, design Property 7); that gating lives at the call sites,
    while this layer only guarantees a normalised ``confidence`` in ``[0, 1]``.

Contract:
    ``extract(image, *, mime_type=None) -> OcrResult`` where ``OcrResult``
    carries ``text``, ``confidence`` (0..1) and ``blocks`` (text regions).
"""
from __future__ import annotations

import hashlib
import json
import re
from abc import ABC, abstractmethod
from typing import List, Optional

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Result contracts
# ---------------------------------------------------------------------------
class OcrBlock(BaseModel):
    """A detected text block / region within the image.

    ``bbox`` is an optional normalised bounding box ``[x0, y0, x1, y1]`` in the
    inclusive range ``[0, 1]`` (fractions of image width/height). ``confidence``
    is normalised to ``[0, 1]`` so downstream confidence-gating (design Property
    7) can treat every provider identically.
    """

    text: str
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    bbox: Optional[List[float]] = None


class OcrResult(BaseModel):
    """Normalised OCR result returned by every ``OcrProvider``.

    ``confidence`` is the overall extraction confidence in ``[0, 1]``; the
    answer-upload surface uses it to decide whether a review/correct/re-upload
    step is required before evaluation (R9.3, R20.1, design Property 7).
    """

    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    blocks: List[OcrBlock] = Field(default_factory=list)
    provider: str = "unknown"


class OcrNotConfiguredError(RuntimeError):
    """Raised when an OCR backend is selected but not available/configured.

    Surfaced as a clear, actionable error rather than a silent bad transcript
    (R20.1): the runtime gateway may not expose a vision/multimodal capability,
    in which case the integration seam fails loudly (analogous to STT's
    :class:`SttNotConfiguredError`).
    """


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
class OcrProvider(ABC):
    """Abstract handwriting OCR provider.

    Implementations extract text from raw image bytes into a normalised
    :class:`OcrResult`. ``mime_type`` is an optional hint about the image
    encoding (e.g. ``"image/png"``, ``"image/jpeg"``) passed through to the
    backend when it can use it.
    """

    name: str = "abstract"

    @abstractmethod
    def extract(
        self,
        image: bytes,
        *,
        mime_type: Optional[str] = None,
    ) -> OcrResult:
        """Extract text from ``image`` into a normalised :class:`OcrResult`."""
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Deterministic mock implementation
# ---------------------------------------------------------------------------
class MockOcrProvider(OcrProvider):
    """Deterministic, dependency-free OCR provider for tests and local/dev.

    Mirrors ``inference.mock_provider.MockProvider`` and
    :class:`~app.core.optional.providers.stt.MockSttProvider`: no network, no
    model. The same ``(image, mime_type)`` input always yields the same output,
    so it is safe for deterministic tests and offline development. ``mime_type``
    is accepted and reflected into the result so callers can verify wiring.
    """

    name = "mock"

    # Threshold-friendly fixed confidence: high enough to represent a "good"
    # extraction by default while remaining deterministic.
    _BASE_CONFIDENCE = 0.92

    def extract(
        self,
        image: bytes,
        *,
        mime_type: Optional[str] = None,
    ) -> OcrResult:
        image = image or b""
        # Derive a stable, opaque token from the input so distinct images yield
        # distinct (but reproducible) text without ever touching a model.
        digest = hashlib.sha256(image).hexdigest()[:8]
        mime = (mime_type or "").strip()
        mime_suffix = f" ({mime})" if mime else ""
        text = f"[MOCK OCR {digest}] simulated handwritten answer{mime_suffix}".strip()

        # Two deterministic blocks so callers can exercise multi-region handling.
        blocks = [
            OcrBlock(
                text=f"[MOCK OCR {digest}] simulated handwritten answer",
                confidence=self._BASE_CONFIDENCE,
                bbox=[0.0, 0.0, 1.0, 0.5],
            ),
            OcrBlock(
                text=f"line 2{mime_suffix}".strip(),
                confidence=self._BASE_CONFIDENCE,
                bbox=[0.0, 0.5, 1.0, 1.0],
            ),
        ]
        return OcrResult(
            text=text,
            confidence=self._BASE_CONFIDENCE,
            blocks=blocks,
            provider="mock/internal",
        )


# ---------------------------------------------------------------------------
# Gemini-Vision implementation (integration seam, via the existing gateway)
# ---------------------------------------------------------------------------
class GeminiVisionOcrProvider(OcrProvider):
    """Gemini-Vision OCR provider routed through the EXISTING inference gateway.

    This is the production integration seam. Per the design decision it reuses
    ``app.core.inference`` (the Gemini provider) rather than introducing a new
    SDK path. The gateway is imported **lazily** inside :meth:`extract` so
    importing this module never requires the gateway/credentials to be present.

    Vision is a *multimodal* capability: the request carries the image bytes
    through to Gemini via the gateway's ``image`` field (Task 9.3 extended the
    shared, previously text-only gateway with this optional, backward-compatible
    seam). With the deterministic mock gateway provider this path runs offline
    (dev/test); with the real Gemini provider it requires vision credentials.

    Failure modes are reported as :class:`OcrNotConfiguredError` (never a silent
    bad transcript — R20.1): if the gateway exposes no vision seam at all, or if
    the configured vision backend is not operational (no creds / call fails),
    the answer-upload UI surfaces the manual-correction / re-upload fallback.
    """

    name = "gemini-vision"

    # OCR instruction. We ask Gemini to return a small JSON object so we can
    # carry a per-extraction confidence and per-line blocks back to the caller;
    # the parser degrades gracefully to plain text if the model returns prose.
    _PROMPT = (
        "You are an OCR engine. Transcribe the handwritten text in this image "
        "exactly as written. Respond with ONLY a JSON object of the form "
        '{"text": "<full transcription>", "confidence": <number between 0 and 1 '
        "estimating how confident you are in the transcription>, "
        '"blocks": [{"text": "<line or region text>", "confidence": <0..1>}]}. '
        "Do not include any commentary or markdown fences."
    )

    def __init__(self, provider_name: str = "gemini"):
        # Which gateway provider to route through (defaults to the real Gemini
        # provider; tests/dev can point the gateway at its own mock).
        self.provider_name = provider_name

    @staticmethod
    def _resolve_gateway():
        """Lazily import the existing inference gateway + request contract.

        Failing to import the gateway is itself a "not configured" condition for
        this seam, so it is reported through :class:`OcrNotConfiguredError`.
        """
        try:
            from app.core.inference.gateway import InferenceGateway
            from app.core.inference.contracts import InferenceRequest
        except Exception as exc:  # pragma: no cover - gateway always importable here
            raise OcrNotConfiguredError(
                "The inference gateway is unavailable; Gemini-Vision OCR cannot "
                "be configured in this environment."
            ) from exc
        return InferenceGateway, InferenceRequest

    @classmethod
    def _gateway_supports_vision(cls, request_cls) -> bool:
        """Return True only if the gateway request can carry image/vision input.

        Task 9.3 extended ``InferenceRequest`` with an optional ``image`` field
        so the gateway is now vision-capable. We still detect the seam by
        inspecting the request contract for a known multimodal field (rather
        than assuming it) so this provider stays correct even if the contract is
        refactored, and so a stripped-down/legacy gateway would still fail
        loudly via :class:`OcrNotConfiguredError` instead of silently.
        """
        fields = set(getattr(request_cls, "model_fields", {}).keys())
        vision_fields = {"image", "image_bytes", "images", "media", "parts", "contents"}
        return bool(fields & vision_fields)

    def extract(
        self,
        image: bytes,
        *,
        mime_type: Optional[str] = None,
    ) -> OcrResult:
        InferenceGateway, InferenceRequest = self._resolve_gateway()

        if not self._gateway_supports_vision(InferenceRequest):
            # The integration seam: the gateway has no multimodal/vision path in
            # this environment, so fail loudly instead of returning a silent bad
            # transcript (R20.1). The answer-upload UI surfaces the fallback.
            raise OcrNotConfiguredError(
                "Gemini-Vision OCR requires a multimodal (vision) capability on "
                "the inference gateway, which is not available in this "
                "environment. Configure the gateway with image input to enable "
                "handwriting OCR, or use the manual-correction fallback."
            )

        # Route the image through the EXISTING (now vision-capable) gateway — no
        # new SDK path. With the deterministic mock gateway provider this works
        # offline; with the real Gemini provider it requires vision credentials.
        try:
            response = InferenceGateway.generate(
                prompt=self._PROMPT,
                provider=self.provider_name,
                temperature=0.0,
                image=image,
                image_mime_type=mime_type,
                response_mime_type="application/json",
            )
        except Exception as exc:
            # No creds / backend not operational in this environment. Surface a
            # clear, actionable error rather than a silent bad transcript so the
            # UI can offer the manual-correction / re-upload fallback (R20.1).
            raise OcrNotConfiguredError(
                "Gemini-Vision OCR call failed; the vision backend is not "
                "operational in this environment (check vision credentials)."
            ) from exc

        return self._normalise(response, mime_type)

    @staticmethod
    def _coerce_confidence(value, *, fallback: float) -> float:
        """Coerce a model-reported confidence into a clamped ``[0, 1]`` float."""
        try:
            conf = float(value)
        except (TypeError, ValueError):
            return fallback
        return max(0.0, min(1.0, conf))

    @classmethod
    def _normalise(cls, response, mime_type: Optional[str]) -> OcrResult:
        """Map a gateway ``InferenceResponse`` into a normalised ``OcrResult``.

        The vision prompt asks Gemini for a small JSON object carrying the full
        transcription, a self-reported ``confidence`` and per-line ``blocks``.
        We parse that here (tolerating markdown fences) and clamp every
        confidence to ``[0, 1]``. If the model returns prose instead of JSON we
        degrade gracefully: the whole response becomes the text and we derive a
        conservative confidence from whether any text came back. The call site
        applies confidence gating (R9.3 / R20.1).
        """
        raw = str(getattr(response, "text", "") or "").strip()
        parsed = cls._parse_json(raw)

        if isinstance(parsed, dict):
            text = str(parsed.get("text", "") or "").strip()
            overall = cls._coerce_confidence(
                parsed.get("confidence"), fallback=0.8 if text else 0.0
            )
            blocks: List[OcrBlock] = []
            for entry in parsed.get("blocks") or []:
                if isinstance(entry, dict) and str(entry.get("text", "")).strip():
                    blocks.append(
                        OcrBlock(
                            text=str(entry["text"]).strip(),
                            confidence=cls._coerce_confidence(
                                entry.get("confidence"), fallback=overall
                            ),
                        )
                    )
            if not blocks and text:
                blocks = [OcrBlock(text=text, confidence=overall)]
            return OcrResult(
                text=text,
                confidence=overall if text else 0.0,
                blocks=blocks,
                provider="google/gemini-vision",
            )

        # Plain-text fallback (model returned prose, not JSON).
        confidence = 0.8 if raw else 0.0
        blocks = [OcrBlock(text=raw, confidence=confidence)] if raw else []
        return OcrResult(
            text=raw,
            confidence=confidence,
            blocks=blocks,
            provider="google/gemini-vision",
        )

    @staticmethod
    def _parse_json(raw: str):
        """Best-effort parse of a JSON object from a model response.

        Tolerates a leading/trailing markdown code fence (```json ... ```),
        which Gemini sometimes emits despite instructions. Returns the parsed
        object, or ``None`` when the response isn't JSON.
        """
        if not raw:
            return None
        candidate = raw.strip()
        if candidate.startswith("```"):
            candidate = candidate.strip("`").strip()
            candidate = re.sub(r"^json", "", candidate, flags=re.IGNORECASE).strip()
        try:
            return json.loads(candidate)
        except (ValueError, TypeError):
            return None


# ---------------------------------------------------------------------------
# Selector / factory (env-driven, like the inference gateway)
# ---------------------------------------------------------------------------
_PROVIDERS: dict = {}


def get_ocr_provider(name: Optional[str] = None) -> OcrProvider:
    """Return an :class:`OcrProvider`, selected by ``name`` or environment.

    Selection precedence:
        1. explicit ``name`` argument
        2. ``OPTIONAL_OCR_PROVIDER`` environment variable
        3. default → ``"mock"``

    The mock is the safe default for test/dev (no model, deterministic), exactly
    like the inference gateway and the STT selector. Providers are cached
    per-name. ``ValueError`` is raised for unknown names.
    """
    import os

    resolved = (name or os.environ.get("OPTIONAL_OCR_PROVIDER") or "mock").strip().lower()

    if resolved in _PROVIDERS:
        return _PROVIDERS[resolved]

    if resolved == "mock":
        provider: OcrProvider = MockOcrProvider()
    elif resolved in ("gemini", "gemini-vision"):
        provider = GeminiVisionOcrProvider()
    else:
        raise ValueError(f"Unknown OCR provider '{resolved}'")

    _PROVIDERS[resolved] = provider
    return provider
