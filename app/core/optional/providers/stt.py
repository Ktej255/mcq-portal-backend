"""Speech-to-text (STT) provider abstraction for the Optional platform.

Mirrors the inference-gateway pattern (interface + concrete impl + deterministic
mock + env-driven selector) used in ``app/core/inference``. Callers depend on the
:class:`SttProvider` interface only, so the concrete backend can be swapped
without touching the answer-writing / recall pipelines (R8.5, R20).

Licensing note (R8.5 — commercially licensed STT only):
    The default production implementation is backed by **OpenAI Whisper**, which
    is released under the **MIT license**. MIT permits unrestricted commercial
    use, so it satisfies the "commercially licensed speech-to-text models"
    constraint. Whisper can run as a hosted API or self-hosted (e.g.
    ``faster-whisper``) and supports ``initial_prompt`` vocabulary biasing —
    used here to bias toward Indian-accented English and per-subject domain
    vocabulary (R20.2).

    A second production option is **Gemini** (:class:`GeminiSttProvider`), routed
    through the existing inference gateway's audio seam. This lets voice run on
    the founder's free Gemini key with no Whisper install. Mock remains the
    deterministic default; Whisper and Gemini are env-selected.

Contract:
    ``transcribe(audio, *, vocabulary_hint=None) -> SttResult`` where
    ``SttResult`` carries ``text``, ``confidence`` (0..1) and ``segments``.
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
class SttSegment(BaseModel):
    """A contiguous span of transcribed speech with timing + per-segment score.

    Timings are in seconds. ``confidence`` is normalised to the inclusive
    range ``[0, 1]`` so downstream confidence-gating (design Property 7) can
    treat every provider identically.
    """

    text: str
    start: float = 0.0
    end: float = 0.0
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class SttResult(BaseModel):
    """Normalised transcription result returned by every ``SttProvider``.

    ``confidence`` is the overall transcript confidence in ``[0, 1]``; the
    answer/recall surfaces use it to decide whether a review/correct step is
    required before evaluation (R8.4, R20.3, design Property 7).
    """

    text: str
    confidence: float = Field(ge=0.0, le=1.0)
    segments: List[SttSegment] = Field(default_factory=list)
    provider: str = "unknown"


class SttNotConfiguredError(RuntimeError):
    """Raised when an STT backend is selected but not available/configured.

    Surfaced as a clear, actionable error rather than a silent bad transcript
    (R20.1/R20.3): the runtime may not have the Whisper library/model/API
    available, in which case the integration seam fails loudly.
    """


# ---------------------------------------------------------------------------
# Interface
# ---------------------------------------------------------------------------
class SttProvider(ABC):
    """Abstract speech-to-text provider.

    Implementations transcribe raw audio bytes into a normalised
    :class:`SttResult`. ``vocabulary_hint`` is an optional list of domain terms
    (per-subject keywords, Indian place/name spellings, etc.) used to bias the
    decoder toward expected vocabulary (R20.2).
    """

    name: str = "abstract"

    @abstractmethod
    def transcribe(
        self,
        audio: bytes,
        *,
        vocabulary_hint: Optional[List[str]] = None,
        mime_type: Optional[str] = None,
    ) -> SttResult:
        """Transcribe ``audio`` to text, optionally biased by ``vocabulary_hint``.

        ``mime_type`` is an optional hint about the audio encoding (e.g.
        ``"audio/webm"``, ``"audio/wav"``, ``"audio/mp4"``) passed through to the
        backend when it can use it (browser ``MediaRecorder`` captures are
        commonly webm/ogg, not wav). It defaults to ``None`` so callers that
        don't know the encoding are unaffected.
        """
        raise NotImplementedError


# ---------------------------------------------------------------------------
# Deterministic mock implementation
# ---------------------------------------------------------------------------
class MockSttProvider(SttProvider):
    """Deterministic, dependency-free STT provider for tests and local/dev.

    Mirrors ``inference.mock_provider.MockProvider``: no network, no model. The
    same ``(audio, vocabulary_hint)`` input always yields the same output, so it
    is safe for deterministic tests and offline development. ``vocabulary_hint``
    is accepted and echoed into the result so callers can verify biasing wiring.
    """

    name = "mock"

    # Threshold-friendly fixed confidence: high enough to represent a "good"
    # transcript by default while remaining deterministic.
    _BASE_CONFIDENCE = 0.95

    def transcribe(
        self,
        audio: bytes,
        *,
        vocabulary_hint: Optional[List[str]] = None,
        mime_type: Optional[str] = None,
    ) -> SttResult:
        audio = audio or b""
        # Derive a stable, opaque token from the input so distinct audio yields
        # distinct (but reproducible) transcripts without ever touching a model.
        digest = hashlib.sha256(audio).hexdigest()[:8]
        hint_terms = [t for t in (vocabulary_hint or []) if t]
        hint_suffix = f" [{', '.join(hint_terms)}]" if hint_terms else ""
        text = f"[MOCK TRANSCRIPT {digest}] simulated spoken answer{hint_suffix}".strip()

        segment = SttSegment(
            text=text,
            start=0.0,
            end=float(max(len(audio), 1)) / 1000.0,
            confidence=self._BASE_CONFIDENCE,
        )
        return SttResult(
            text=text,
            confidence=self._BASE_CONFIDENCE,
            segments=[segment],
            provider="mock/internal",
        )


# ---------------------------------------------------------------------------
# Whisper-backed implementation (integration seam)
# ---------------------------------------------------------------------------
class WhisperSttProvider(SttProvider):
    """Whisper-backed STT provider (MIT-licensed — see module docstring).

    This is the production integration seam. The Whisper dependency is imported
    **lazily** inside :meth:`transcribe` so importing this module never requires
    audio models to be installed. If the library/model/API is unavailable the
    provider raises :class:`SttNotConfiguredError` with a clear message rather
    than failing obscurely or returning a silent bad transcript.

    ``vocabulary_hint`` is passed through as Whisper's ``initial_prompt`` to bias
    decoding toward Indian-accented English and per-subject domain vocabulary
    (R20.2).
    """

    name = "whisper"

    def __init__(self, model_name: str = "base", language: Optional[str] = "en"):
        self.model_name = model_name
        self.language = language
        self._model = None  # lazily loaded

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            import whisper  # type: ignore  # lazy import: MIT-licensed openai-whisper
        except Exception as exc:  # pragma: no cover - depends on optional dep
            raise SttNotConfiguredError(
                "Whisper STT is not available in this environment. Install the "
                "MIT-licensed 'openai-whisper' (or a 'faster-whisper' adapter) "
                "and ensure the model can be loaded to enable speech-to-text."
            ) from exc
        try:
            self._model = whisper.load_model(self.model_name)
        except Exception as exc:  # pragma: no cover - depends on optional dep
            raise SttNotConfiguredError(
                f"Failed to load Whisper model '{self.model_name}'. The STT "
                "backend is not configured."
            ) from exc
        return self._model

    @staticmethod
    def _build_initial_prompt(vocabulary_hint: Optional[List[str]]) -> Optional[str]:
        """Turn the vocabulary hint into a Whisper ``initial_prompt`` string."""
        terms = [t.strip() for t in (vocabulary_hint or []) if t and t.strip()]
        if not terms:
            return None
        # A short comma-joined list of expected terms biases the decoder toward
        # this vocabulary without dictating the output.
        return "Vocabulary: " + ", ".join(terms)

    def transcribe(
        self,
        audio: bytes,
        *,
        vocabulary_hint: Optional[List[str]] = None,
        mime_type: Optional[str] = None,
    ) -> SttResult:
        model = self._load_model()
        initial_prompt = self._build_initial_prompt(vocabulary_hint)

        # Whisper decodes the audio container itself (via ffmpeg) from the file
        # bytes, so ``mime_type`` is accepted for interface parity but not needed
        # here. We persist the raw bytes to a temp file and let Whisper detect
        # the format.
        import tempfile
        import os

        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".audio", delete=False) as tmp:
                tmp.write(audio or b"")
                tmp_path = tmp.name
            try:
                result = model.transcribe(  # pragma: no cover - requires model
                    tmp_path,
                    language=self.language,
                    initial_prompt=initial_prompt,
                )
            except Exception as exc:  # pragma: no cover - requires model
                raise SttNotConfiguredError(
                    "Whisper transcription failed; STT backend is not "
                    "operational in this environment."
                ) from exc
        finally:
            if tmp_path and os.path.exists(tmp_path):
                os.unlink(tmp_path)

        return self._normalise(result)  # pragma: no cover - requires model

    @staticmethod
    def _normalise(raw: dict) -> SttResult:  # pragma: no cover - requires model
        """Map Whisper's raw output dict into the normalised ``SttResult``.

        Whisper reports per-segment ``avg_logprob`` (a log-probability, not a
        0..1 score); we map it through a bounded transform so ``confidence``
        always lands in ``[0, 1]`` as the contract requires.
        """
        import math

        raw_segments = raw.get("segments", []) or []
        segments: List[SttSegment] = []
        confidences: List[float] = []
        for seg in raw_segments:
            avg_logprob = float(seg.get("avg_logprob", 0.0))
            conf = 1.0 / (1.0 + math.exp(-avg_logprob))  # logistic -> (0,1)
            conf = max(0.0, min(1.0, conf))
            confidences.append(conf)
            segments.append(
                SttSegment(
                    text=str(seg.get("text", "")).strip(),
                    start=float(seg.get("start", 0.0)),
                    end=float(seg.get("end", 0.0)),
                    confidence=conf,
                )
            )

        overall = sum(confidences) / len(confidences) if confidences else 0.0
        return SttResult(
            text=str(raw.get("text", "")).strip(),
            confidence=max(0.0, min(1.0, overall)),
            segments=segments,
            provider="openai/whisper",
        )


# ---------------------------------------------------------------------------
# Gemini-backed implementation (integration seam, via the existing gateway)
# ---------------------------------------------------------------------------
class GeminiSttProvider(SttProvider):
    """Gemini STT provider routed through the EXISTING inference gateway.

    This lets voice / speech-to-text run on the founder's free Gemini key with
    **no Whisper install** — Gemini 1.5 accepts inline audio alongside a text
    prompt. Exactly like :class:`~app.core.optional.providers.ocr.GeminiVisionOcrProvider`
    reuses the gateway's optional ``image`` field for vision, this provider
    reuses the gateway's optional ``audio`` field for transcription rather than
    introducing a new SDK path. The gateway is imported **lazily** inside
    :meth:`transcribe` so importing this module never requires the gateway or
    credentials to be present.

    ``vocabulary_hint`` is folded into the prompt to bias the transcription
    toward Indian-accented English and per-subject domain vocabulary (R20.2).

    Failure modes are reported as :class:`SttNotConfiguredError` (never a silent
    bad transcript — R20.1/R20.3): if the gateway exposes no audio seam at all,
    or if the configured backend is not operational (no creds / call fails), the
    answer / recall UI surfaces the manual-type / re-record fallback.
    """

    name = "gemini"

    # Transcription instruction. We ask Gemini to return a small JSON object so
    # we can carry a per-transcription confidence and per-segment data back to
    # the caller; the parser degrades gracefully to plain text if the model
    # returns prose.
    _PROMPT = (
        "You are a speech-to-text engine. Transcribe the spoken words in this "
        "audio exactly as said, in English. Respond with ONLY a JSON object of "
        'the form {"text": "<full transcription>", "confidence": <number between '
        "0 and 1 estimating how confident you are in the transcription>, "
        '"segments": [{"text": "<segment text>", "start": <seconds>, "end": '
        "<seconds>, \"confidence\": <0..1>}]}. Do not include any commentary or "
        "markdown fences."
    )

    def __init__(self, provider_name: str = "gemini"):
        # Which gateway provider to route through (defaults to the real Gemini
        # provider; tests/dev can point the gateway at its own mock).
        self.provider_name = provider_name

    @staticmethod
    def _resolve_gateway():
        """Lazily import the existing inference gateway + request contract.

        Failing to import the gateway is itself a "not configured" condition for
        this seam, so it is reported through :class:`SttNotConfiguredError`.
        """
        try:
            from app.core.inference.gateway import InferenceGateway
            from app.core.inference.contracts import InferenceRequest
        except Exception as exc:  # pragma: no cover - gateway always importable here
            raise SttNotConfiguredError(
                "The inference gateway is unavailable; Gemini STT cannot be "
                "configured in this environment."
            ) from exc
        return InferenceGateway, InferenceRequest

    @classmethod
    def _gateway_supports_audio(cls, request_cls) -> bool:
        """Return True only if the gateway request can carry audio input.

        We detect the seam by inspecting the request contract for a known audio
        field (rather than assuming it) so this provider stays correct even if
        the contract is refactored, and so a stripped-down/legacy gateway would
        still fail loudly via :class:`SttNotConfiguredError` instead of silently.
        """
        fields = set(getattr(request_cls, "model_fields", {}).keys())
        audio_fields = {"audio", "audio_bytes", "audios", "media", "parts", "contents"}
        return bool(fields & audio_fields)

    def _build_prompt(self, vocabulary_hint: Optional[List[str]]) -> str:
        """Append the vocabulary hint (if any) to the base transcription prompt."""
        terms = [t.strip() for t in (vocabulary_hint or []) if t and t.strip()]
        if not terms:
            return self._PROMPT
        # A short comma-joined list of expected terms biases decoding toward this
        # vocabulary without dictating the output (R20.2).
        return self._PROMPT + " Expected vocabulary: " + ", ".join(terms) + "."

    def transcribe(
        self,
        audio: bytes,
        *,
        vocabulary_hint: Optional[List[str]] = None,
        mime_type: Optional[str] = None,
    ) -> SttResult:
        InferenceGateway, InferenceRequest = self._resolve_gateway()

        if not self._gateway_supports_audio(InferenceRequest):
            # The integration seam: the gateway has no multimodal/audio path in
            # this environment, so fail loudly instead of returning a silent bad
            # transcript (R20.1/R20.3). The UI surfaces the manual-type fallback.
            raise SttNotConfiguredError(
                "Gemini STT requires a multimodal (audio) capability on the "
                "inference gateway, which is not available in this environment. "
                "Configure the gateway with audio input to enable speech-to-text, "
                "or use the manual-type fallback."
            )

        # Route the audio through the EXISTING (now audio-capable) gateway — no
        # new SDK path. With the deterministic mock gateway provider this works
        # offline; with the real Gemini provider it requires valid credentials.
        try:
            response = InferenceGateway.generate(
                prompt=self._build_prompt(vocabulary_hint),
                provider=self.provider_name,
                temperature=0.0,
                audio=audio,
                audio_mime_type=mime_type,
                response_mime_type="application/json",
            )
        except Exception as exc:
            # No creds / backend not operational in this environment. Surface a
            # clear, actionable error rather than a silent bad transcript so the
            # UI can offer the manual-type / re-record fallback (R20.1/R20.3).
            raise SttNotConfiguredError(
                "Gemini STT call failed; the audio backend is not operational in "
                "this environment (check Gemini credentials)."
            ) from exc

        return self._normalise(response)

    @staticmethod
    def _coerce_confidence(value, *, fallback: float) -> float:
        """Coerce a model-reported confidence into a clamped ``[0, 1]`` float."""
        try:
            conf = float(value)
        except (TypeError, ValueError):
            return fallback
        return max(0.0, min(1.0, conf))

    @classmethod
    def _normalise(cls, response) -> SttResult:
        """Map a gateway ``InferenceResponse`` into a normalised ``SttResult``.

        The audio prompt asks Gemini for a small JSON object carrying the full
        transcription, a self-reported ``confidence`` and per-segment data. We
        parse that here (tolerating markdown fences) and clamp every confidence
        to ``[0, 1]``. If the model returns prose instead of JSON we degrade
        gracefully: the whole response becomes the text and we derive a
        conservative confidence from whether any text came back. The call site
        applies confidence gating (R8.4 / R20.3).
        """
        raw = str(getattr(response, "text", "") or "").strip()
        parsed = cls._parse_json(raw)

        if isinstance(parsed, dict):
            text = str(parsed.get("text", "") or "").strip()
            overall = cls._coerce_confidence(
                parsed.get("confidence"), fallback=0.8 if text else 0.0
            )
            segments: List[SttSegment] = []
            for entry in parsed.get("segments") or []:
                if isinstance(entry, dict) and str(entry.get("text", "")).strip():
                    segments.append(
                        SttSegment(
                            text=str(entry["text"]).strip(),
                            start=float(entry.get("start", 0.0) or 0.0),
                            end=float(entry.get("end", 0.0) or 0.0),
                            confidence=cls._coerce_confidence(
                                entry.get("confidence"), fallback=overall
                            ),
                        )
                    )
            if not segments and text:
                segments = [SttSegment(text=text, confidence=overall)]
            return SttResult(
                text=text,
                confidence=overall if text else 0.0,
                segments=segments,
                provider="google/gemini-audio",
            )

        # Plain-text fallback (model returned prose, not JSON).
        confidence = 0.8 if raw else 0.0
        segments = [SttSegment(text=raw, confidence=confidence)] if raw else []
        return SttResult(
            text=raw,
            confidence=confidence,
            segments=segments,
            provider="google/gemini-audio",
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


def get_stt_provider(name: Optional[str] = None) -> SttProvider:
    """Return an :class:`SttProvider`, selected by ``name`` or environment.

    Selection precedence:
        1. explicit ``name`` argument
        2. ``OPTIONAL_STT_PROVIDER`` environment variable
        3. default → ``"mock"``

    The mock is the safe default for test/dev (no model, deterministic), exactly
    like the inference gateway defaults. Self-hosted ``whisper`` (MIT) and
    gateway-routed ``gemini`` (the founder's free key, no Whisper install) are
    both available. Providers are cached per-name so a model is loaded at most
    once. ``ValueError`` is raised for unknown names.
    """
    import os

    resolved = (name or os.environ.get("OPTIONAL_STT_PROVIDER") or "mock").strip().lower()

    if resolved in _PROVIDERS:
        return _PROVIDERS[resolved]

    if resolved == "mock":
        provider: SttProvider = MockSttProvider()
    elif resolved == "whisper":
        provider = WhisperSttProvider()
    elif resolved == "gemini":
        provider = GeminiSttProvider()
    else:
        raise ValueError(f"Unknown STT provider '{resolved}'")

    _PROVIDERS[resolved] = provider
    return provider
