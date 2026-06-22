"""Tests for the ``GeminiVisionOcrProvider`` real OCR path against a vision-
capable gateway (Task 9.3 — R9.1 / R20.1).

The provider routes the image through the EXISTING inference gateway (extended
with an optional ``image`` field in Task 9.3) and parses the model's structured
response into a normalised ``OcrResult{text, confidence, blocks}``. Here we
point the provider at the gateway's deterministic ``mock`` provider so the full
route — gateway vision branch → JSON parse → normalised result — runs offline,
no credentials, no network.

We also assert the JSON-parsing/normalisation logic directly (markdown-fence
tolerance, confidence clamping, prose fallback) and that a non-operational
backend surfaces ``OcrNotConfiguredError`` rather than a silent bad result.
"""

from __future__ import annotations

import pytest

from app.core.inference.contracts import InferenceResponse
from app.core.optional.providers import (
    GeminiVisionOcrProvider,
    OcrResult,
    OcrNotConfiguredError,
)


# ---------------------------------------------------------------------------
# Real path against the mock vision gateway (provider_name="mock")
# ---------------------------------------------------------------------------
def test_extract_routes_through_mock_vision_gateway():
    provider = GeminiVisionOcrProvider(provider_name="mock")
    result = provider.extract(b"handwriting-image", mime_type="image/png")

    assert isinstance(result, OcrResult)
    assert result.provider == "google/gemini-vision"
    assert result.text  # transcription came back
    assert 0.0 <= result.confidence <= 1.0
    assert result.blocks and result.blocks[0].text


def test_extract_is_deterministic_against_mock_gateway():
    provider = GeminiVisionOcrProvider(provider_name="mock")
    first = provider.extract(b"same-image")
    second = provider.extract(b"same-image")
    assert first.text == second.text
    assert first.confidence == second.confidence


# ---------------------------------------------------------------------------
# Normalisation / parsing logic (drive _normalise with stub responses)
# ---------------------------------------------------------------------------
def _resp(text: str) -> InferenceResponse:
    return InferenceResponse(text=text, provider="mock/internal-vision")


def test_normalise_parses_json_payload():
    payload = '{"text": "the answer", "confidence": 0.91, "blocks": [{"text": "the answer", "confidence": 0.91}]}'
    result = GeminiVisionOcrProvider._normalise(_resp(payload), "image/png")
    assert result.text == "the answer"
    assert result.confidence == pytest.approx(0.91)
    assert result.blocks[0].text == "the answer"


def test_normalise_tolerates_markdown_fences():
    payload = '```json\n{"text": "fenced", "confidence": 0.7}\n```'
    result = GeminiVisionOcrProvider._normalise(_resp(payload), None)
    assert result.text == "fenced"
    assert result.confidence == pytest.approx(0.7)
    # No blocks in payload -> a single block is synthesised from the text.
    assert result.blocks and result.blocks[0].text == "fenced"


def test_normalise_clamps_out_of_range_confidence():
    result = GeminiVisionOcrProvider._normalise(
        _resp('{"text": "x", "confidence": 5}'), None
    )
    assert 0.0 <= result.confidence <= 1.0


def test_normalise_prose_fallback_when_not_json():
    result = GeminiVisionOcrProvider._normalise(_resp("just plain transcription"), None)
    assert result.text == "just plain transcription"
    assert 0.0 < result.confidence <= 1.0
    assert result.blocks[0].text == "just plain transcription"


def test_normalise_empty_response_is_zero_confidence():
    result = GeminiVisionOcrProvider._normalise(_resp(""), None)
    assert result.text == ""
    assert result.confidence == 0.0
    assert result.blocks == []


# ---------------------------------------------------------------------------
# Non-operational backend -> loud failure, never a silent bad result (R20.1)
# ---------------------------------------------------------------------------
def test_extract_raises_not_configured_when_gateway_call_fails(monkeypatch):
    # Force the gateway call to blow up (e.g. missing creds / network) and prove
    # the provider surfaces OcrNotConfiguredError rather than a bad transcript.
    from app.core.inference.gateway import InferenceGateway

    def _boom(*args, **kwargs):
        raise RuntimeError("no vision credentials")

    monkeypatch.setattr(InferenceGateway, "generate", staticmethod(_boom))
    provider = GeminiVisionOcrProvider(provider_name="gemini")
    with pytest.raises(OcrNotConfiguredError):
        provider.extract(b"image", mime_type="image/png")
