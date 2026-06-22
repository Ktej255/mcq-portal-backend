"""Tests for the Optional platform STT provider abstraction (Task 3.1).

Covers the deterministic mock provider (deterministic output, confidence in
[0, 1], vocabulary_hint accepted, segments shape) and the env-driven selector
(returns the mock by default). The Whisper integration seam is exercised only
for its environment-independent helpers/guards — actual transcription requires
an audio model that is not present in this environment.

Requirements: 8.2, 8.5, 20.2.
"""
import importlib

import pytest

from app.core.optional.providers import (
    MockSttProvider,
    SttNotConfiguredError,
    SttProvider,
    SttResult,
    SttSegment,
    WhisperSttProvider,
    GeminiSttProvider,
    get_stt_provider,
)
from app.core.optional.providers import stt as stt_module


# ---------------------------------------------------------------------------
# Mock provider — deterministic output
# ---------------------------------------------------------------------------
def test_mock_transcribe_is_deterministic_for_same_input():
    provider = MockSttProvider()
    audio = b"some-audio-bytes"
    first = provider.transcribe(audio)
    second = provider.transcribe(audio)
    assert first.text == second.text
    assert first.confidence == second.confidence
    assert [s.model_dump() for s in first.segments] == [s.model_dump() for s in second.segments]


def test_mock_transcribe_distinct_inputs_yield_distinct_text():
    provider = MockSttProvider()
    a = provider.transcribe(b"audio-a")
    b = provider.transcribe(b"audio-b")
    assert a.text != b.text


def test_mock_transcribe_returns_sttresult_shape():
    result = MockSttProvider().transcribe(b"audio")
    assert isinstance(result, SttResult)
    assert isinstance(result.text, str) and result.text
    assert isinstance(result.confidence, float)
    assert isinstance(result.segments, list)
    assert result.segments and isinstance(result.segments[0], SttSegment)


def test_mock_confidence_within_unit_interval():
    result = MockSttProvider().transcribe(b"audio")
    assert 0.0 <= result.confidence <= 1.0
    for seg in result.segments:
        assert 0.0 <= seg.confidence <= 1.0


def test_mock_handles_empty_audio_without_error():
    result = MockSttProvider().transcribe(b"")
    assert isinstance(result, SttResult)
    assert 0.0 <= result.confidence <= 1.0
    assert result.segments  # still produces a (deterministic) segment


# ---------------------------------------------------------------------------
# Mock provider — vocabulary_hint support (R20.2)
# ---------------------------------------------------------------------------
def test_mock_accepts_vocabulary_hint_and_reflects_it():
    provider = MockSttProvider()
    hint = ["Brahmaputra", "isostasy", "monsoon"]
    result = provider.transcribe(b"audio", vocabulary_hint=hint)
    assert isinstance(result, SttResult)
    for term in hint:
        assert term in result.text


def test_mock_vocabulary_hint_is_optional():
    # No hint provided -> still valid, and differs from the hinted output.
    no_hint = MockSttProvider().transcribe(b"audio")
    with_hint = MockSttProvider().transcribe(b"audio", vocabulary_hint=["isostasy"])
    assert no_hint.text != with_hint.text


def test_mock_segments_have_expected_fields():
    result = MockSttProvider().transcribe(b"audio")
    seg = result.segments[0]
    assert hasattr(seg, "text") and hasattr(seg, "start")
    assert hasattr(seg, "end") and hasattr(seg, "confidence")
    assert seg.end >= seg.start


# ---------------------------------------------------------------------------
# SttResult / SttSegment validation guards confidence to [0, 1]
# ---------------------------------------------------------------------------
def test_sttresult_rejects_out_of_range_confidence():
    with pytest.raises(Exception):
        SttResult(text="x", confidence=1.5)
    with pytest.raises(Exception):
        SttResult(text="x", confidence=-0.1)


# ---------------------------------------------------------------------------
# Selector / factory
# ---------------------------------------------------------------------------
def test_selector_returns_mock_by_default(monkeypatch):
    monkeypatch.delenv("OPTIONAL_STT_PROVIDER", raising=False)
    stt_module._PROVIDERS.clear()
    provider = get_stt_provider()
    assert isinstance(provider, MockSttProvider)
    assert isinstance(provider, SttProvider)


def test_selector_explicit_mock(monkeypatch):
    stt_module._PROVIDERS.clear()
    assert isinstance(get_stt_provider("mock"), MockSttProvider)


def test_selector_env_driven_whisper(monkeypatch):
    monkeypatch.setenv("OPTIONAL_STT_PROVIDER", "whisper")
    stt_module._PROVIDERS.clear()
    provider = get_stt_provider()
    assert isinstance(provider, WhisperSttProvider)


def test_selector_env_driven_gemini(monkeypatch):
    monkeypatch.setenv("OPTIONAL_STT_PROVIDER", "gemini")
    stt_module._PROVIDERS.clear()
    provider = get_stt_provider()
    assert isinstance(provider, GeminiSttProvider)
    assert isinstance(provider, SttProvider)


def test_selector_caches_instances():
    stt_module._PROVIDERS.clear()
    assert get_stt_provider("mock") is get_stt_provider("mock")


def test_selector_unknown_provider_raises():
    stt_module._PROVIDERS.clear()
    with pytest.raises(ValueError):
        get_stt_provider("does-not-exist")


# ---------------------------------------------------------------------------
# Whisper seam — environment-independent behaviour
# ---------------------------------------------------------------------------
def test_whisper_initial_prompt_builder():
    build = WhisperSttProvider._build_initial_prompt
    assert build(None) is None
    assert build([]) is None
    assert build(["", "  "]) is None
    prompt = build(["Brahmaputra", "isostasy"])
    assert prompt is not None
    assert "Brahmaputra" in prompt and "isostasy" in prompt


def test_whisper_raises_not_configured_when_library_missing(monkeypatch):
    # Force the lazy import inside _load_model to fail, simulating an env with
    # no audio model installed; the seam must fail loudly (R20.1/R20.3).
    import builtins

    real_import = builtins.__import__

    def fake_import(name, *args, **kwargs):
        if name == "whisper":
            raise ImportError("no whisper here")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    provider = WhisperSttProvider()
    with pytest.raises(SttNotConfiguredError):
        provider.transcribe(b"audio", vocabulary_hint=["isostasy"])


def test_provider_module_does_not_reference_gs_geography():
    # Hard isolation constraint (Requirement 2 / Property 9).
    mod = importlib.import_module("app.core.optional.providers.stt")
    source_file = getattr(mod, "__file__", "") or ""
    assert "geography" not in source_file.lower()


# ---------------------------------------------------------------------------
# Gemini seam — routes through the EXISTING (now audio-capable) gateway.
# The gateway's InferenceRequest carries an optional `audio` field (mirroring
# the `image`/vision seam), so transcription can run on the founder's free
# Gemini key with no Whisper install. It still fails loudly if a legacy/
# stripped gateway exposes no audio field (R20.1/R20.3).
# ---------------------------------------------------------------------------
def test_gemini_uses_existing_gateway_contract():
    # Confirm the seam resolves the EXISTING inference gateway/contract rather
    # than introducing a new SDK path.
    from app.core.inference.gateway import InferenceGateway
    from app.core.inference.contracts import InferenceRequest

    gateway_cls, request_cls = GeminiSttProvider._resolve_gateway()
    assert gateway_cls is InferenceGateway
    assert request_cls is InferenceRequest
    # The contract now carries an optional `audio` field, so audio is available.
    assert GeminiSttProvider._gateway_supports_audio(request_cls) is True


def test_gemini_detects_audio_seam_when_present():
    class _AudioRequest:
        model_fields = {"prompt": None, "audio": None}

    assert GeminiSttProvider._gateway_supports_audio(_AudioRequest) is True


def test_gemini_raises_not_configured_without_audio_seam(monkeypatch):
    # Simulate a gateway whose request contract exposes NO audio field:
    # transcribe() must raise a clear SttNotConfiguredError rather than a silent
    # bad transcript (graceful failure when no creds/seam — R20.1/R20.3).
    provider = GeminiSttProvider()
    monkeypatch.setattr(
        GeminiSttProvider,
        "_gateway_supports_audio",
        classmethod(lambda cls, rc: False),
    )
    with pytest.raises(SttNotConfiguredError):
        provider.transcribe(b"audio-bytes", vocabulary_hint=["isostasy"])


def test_gemini_transcribes_via_mock_gateway():
    # Route through the gateway's deterministic MOCK provider (no creds): the
    # audio path returns a structured JSON transcript which the provider
    # normalises into an SttResult.
    provider = GeminiSttProvider(provider_name="mock")
    result = provider.transcribe(b"some-audio-bytes")
    assert isinstance(result, SttResult)
    assert result.text
    assert 0.0 <= result.confidence <= 1.0
    assert result.segments and isinstance(result.segments[0], SttSegment)
    assert result.provider == "google/gemini-audio"


def test_gemini_mock_gateway_path_is_deterministic():
    provider = GeminiSttProvider(provider_name="mock")
    first = provider.transcribe(b"same-audio")
    second = provider.transcribe(b"same-audio")
    assert first.text == second.text
    assert first.confidence == second.confidence


def test_gemini_forwards_mime_type_to_gateway(monkeypatch):
    # The real audio encoding (e.g. browser webm) must reach the gateway as
    # `audio_mime_type` so Gemini decodes it correctly — not be dropped/defaulted.
    from app.core.inference.gateway import InferenceGateway
    from app.core.optional.providers.stt import SttResult, SttSegment

    captured = {}

    def fake_generate(prompt, provider=None, **kwargs):
        captured.update(kwargs)

        class _Resp:
            text = '{"text": "ok", "confidence": 0.9}'

        return _Resp()

    monkeypatch.setattr(InferenceGateway, "generate", staticmethod(fake_generate))
    provider = GeminiSttProvider()
    provider.transcribe(b"audio", mime_type="audio/webm")
    assert captured.get("audio_mime_type") == "audio/webm"
    assert captured.get("audio") == b"audio"


def test_gemini_mime_type_defaults_to_none_when_unknown(monkeypatch):
    # When the caller doesn't know the encoding, None is forwarded (the gateway
    # provider applies its own sensible default) — never a wrong hard-coded type.
    from app.core.inference.gateway import InferenceGateway

    captured = {}

    def fake_generate(prompt, provider=None, **kwargs):
        captured.update(kwargs)

        class _Resp:
            text = '{"text": "ok", "confidence": 0.9}'

        return _Resp()

    monkeypatch.setattr(InferenceGateway, "generate", staticmethod(fake_generate))
    GeminiSttProvider().transcribe(b"audio")
    assert captured.get("audio_mime_type") is None


def test_gemini_build_prompt_includes_vocabulary_hint():
    provider = GeminiSttProvider()
    base = provider._build_prompt(None)
    assert provider._build_prompt([]) == base
    hinted = provider._build_prompt(["Brahmaputra", "isostasy"])
    assert "Brahmaputra" in hinted and "isostasy" in hinted
    assert len(hinted) > len(base)


def test_gemini_raises_not_configured_when_gateway_call_fails(monkeypatch):
    # A real backend with no creds raises on generate(); the seam must convert
    # that into a clear SttNotConfiguredError, never a silent bad transcript.
    from app.core.inference.gateway import InferenceGateway

    def boom(*args, **kwargs):
        raise RuntimeError("no credentials")

    monkeypatch.setattr(InferenceGateway, "generate", staticmethod(boom))
    provider = GeminiSttProvider()
    with pytest.raises(SttNotConfiguredError):
        provider.transcribe(b"audio")


def test_gemini_normalise_degrades_on_prose_response():
    # If the model returns prose instead of JSON, normalisation degrades
    # gracefully: text is preserved, confidence stays bounded.
    class _Resp:
        text = "the himalayas are fold mountains"

    result = GeminiSttProvider._normalise(_Resp())
    assert result.text == "the himalayas are fold mountains"
    assert 0.0 <= result.confidence <= 1.0
    assert result.segments


def test_gemini_normalise_empty_response_is_zero_confidence():
    class _Resp:
        text = ""

    result = GeminiSttProvider._normalise(_Resp())
    assert result.text == ""
    assert result.confidence == 0.0
    assert result.segments == []
