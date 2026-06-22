"""Tests for the Optional platform OCR provider abstraction (Task 3.2).

Covers the deterministic mock provider (deterministic output, confidence in
[0, 1], blocks shape, mime handling) and the env-driven selector (returns the
mock by default). The Gemini-Vision integration seam is exercised for its
environment-independent behaviour: it resolves the EXISTING inference gateway
(now extended with an optional ``image`` field — Task 9.3) and reports vision as
available; if a legacy/stripped gateway exposed no vision field it must raise a
clear ``OcrNotConfiguredError`` rather than returning a silent bad transcript
(R20.1). A GS-isolation guard (Requirement 2 / Property 9) is included.

Requirements: 9.1, 20.1.
"""
import importlib

import pytest

from app.core.optional.providers import (
    GeminiVisionOcrProvider,
    MockOcrProvider,
    OcrBlock,
    OcrNotConfiguredError,
    OcrProvider,
    OcrResult,
    get_ocr_provider,
)
from app.core.optional.providers import ocr as ocr_module


# ---------------------------------------------------------------------------
# Mock provider — deterministic output
# ---------------------------------------------------------------------------
def test_mock_extract_is_deterministic_for_same_input():
    provider = MockOcrProvider()
    image = b"some-image-bytes"
    first = provider.extract(image)
    second = provider.extract(image)
    assert first.text == second.text
    assert first.confidence == second.confidence
    assert [b.model_dump() for b in first.blocks] == [b.model_dump() for b in second.blocks]


def test_mock_extract_distinct_inputs_yield_distinct_text():
    provider = MockOcrProvider()
    a = provider.extract(b"image-a")
    b = provider.extract(b"image-b")
    assert a.text != b.text


def test_mock_extract_returns_ocrresult_shape():
    result = MockOcrProvider().extract(b"image")
    assert isinstance(result, OcrResult)
    assert isinstance(result.text, str) and result.text
    assert isinstance(result.confidence, float)
    assert isinstance(result.blocks, list)
    assert result.blocks and isinstance(result.blocks[0], OcrBlock)


def test_mock_confidence_within_unit_interval():
    result = MockOcrProvider().extract(b"image")
    assert 0.0 <= result.confidence <= 1.0
    for block in result.blocks:
        assert 0.0 <= block.confidence <= 1.0


def test_mock_handles_empty_image_without_error():
    result = MockOcrProvider().extract(b"")
    assert isinstance(result, OcrResult)
    assert 0.0 <= result.confidence <= 1.0
    assert result.blocks  # still produces (deterministic) blocks


# ---------------------------------------------------------------------------
# Mock provider — blocks shape + mime handling
# ---------------------------------------------------------------------------
def test_mock_blocks_have_expected_fields():
    result = MockOcrProvider().extract(b"image")
    block = result.blocks[0]
    assert hasattr(block, "text") and hasattr(block, "confidence")
    assert hasattr(block, "bbox")
    # bbox is a normalised [x0, y0, x1, y1] box in [0, 1].
    assert block.bbox is not None and len(block.bbox) == 4
    for coord in block.bbox:
        assert 0.0 <= coord <= 1.0


def test_mock_accepts_mime_type_and_reflects_it():
    provider = MockOcrProvider()
    result = provider.extract(b"image", mime_type="image/png")
    assert isinstance(result, OcrResult)
    assert "image/png" in result.text


def test_mock_mime_type_is_optional():
    # No mime provided -> still valid, and differs from the mime-tagged output.
    no_mime = MockOcrProvider().extract(b"image")
    with_mime = MockOcrProvider().extract(b"image", mime_type="image/jpeg")
    assert no_mime.text != with_mime.text


# ---------------------------------------------------------------------------
# OcrResult / OcrBlock validation guards confidence to [0, 1]
# ---------------------------------------------------------------------------
def test_ocrresult_rejects_out_of_range_confidence():
    with pytest.raises(Exception):
        OcrResult(text="x", confidence=1.5)
    with pytest.raises(Exception):
        OcrResult(text="x", confidence=-0.1)


def test_ocrblock_rejects_out_of_range_confidence():
    with pytest.raises(Exception):
        OcrBlock(text="x", confidence=2.0)


# ---------------------------------------------------------------------------
# Selector / factory
# ---------------------------------------------------------------------------
def test_selector_returns_mock_by_default(monkeypatch):
    monkeypatch.delenv("OPTIONAL_OCR_PROVIDER", raising=False)
    ocr_module._PROVIDERS.clear()
    provider = get_ocr_provider()
    assert isinstance(provider, MockOcrProvider)
    assert isinstance(provider, OcrProvider)


def test_selector_explicit_mock(monkeypatch):
    ocr_module._PROVIDERS.clear()
    assert isinstance(get_ocr_provider("mock"), MockOcrProvider)


def test_selector_env_driven_gemini_vision(monkeypatch):
    monkeypatch.setenv("OPTIONAL_OCR_PROVIDER", "gemini-vision")
    ocr_module._PROVIDERS.clear()
    provider = get_ocr_provider()
    assert isinstance(provider, GeminiVisionOcrProvider)


def test_selector_gemini_alias(monkeypatch):
    ocr_module._PROVIDERS.clear()
    assert isinstance(get_ocr_provider("gemini"), GeminiVisionOcrProvider)


def test_selector_caches_instances():
    ocr_module._PROVIDERS.clear()
    assert get_ocr_provider("mock") is get_ocr_provider("mock")


def test_selector_unknown_provider_raises():
    ocr_module._PROVIDERS.clear()
    with pytest.raises(ValueError):
        get_ocr_provider("does-not-exist")


# ---------------------------------------------------------------------------
# Gemini-Vision seam — reuses the existing (now vision-capable) gateway.
# Task 9.3 extended InferenceRequest with an optional `image` field, so the
# seam is now available; it still fails loudly if a legacy/stripped gateway
# exposes no vision field (R20.1).
# ---------------------------------------------------------------------------
def test_gemini_vision_raises_not_configured_without_vision_seam(monkeypatch):
    # Simulate a gateway whose request contract exposes NO multimodal field:
    # extract() must raise a clear OcrNotConfiguredError rather than a silent
    # bad result.
    provider = GeminiVisionOcrProvider()
    monkeypatch.setattr(
        GeminiVisionOcrProvider, "_gateway_supports_vision", classmethod(lambda cls, rc: False)
    )
    with pytest.raises(OcrNotConfiguredError):
        provider.extract(b"image-bytes", mime_type="image/png")


def test_gemini_vision_uses_existing_gateway_contract():
    # Confirm the seam resolves the EXISTING inference gateway/contract rather
    # than introducing a new SDK path.
    from app.core.inference.gateway import InferenceGateway
    from app.core.inference.contracts import InferenceRequest

    gateway_cls, request_cls = GeminiVisionOcrProvider._resolve_gateway()
    assert gateway_cls is InferenceGateway
    assert request_cls is InferenceRequest
    # The contract now carries an optional `image` field, so vision is available.
    assert GeminiVisionOcrProvider._gateway_supports_vision(request_cls) is True


def test_gemini_vision_detects_vision_seam_when_present():
    # If/when the gateway request contract gains a multimodal field, the seam
    # should report vision as available (forward-compatibility, no SDK change).
    class _VisionRequest:
        model_fields = {"prompt": None, "image": None}

    assert GeminiVisionOcrProvider._gateway_supports_vision(_VisionRequest) is True


# ---------------------------------------------------------------------------
# GS Geography isolation (Requirement 2 / Property 9)
# ---------------------------------------------------------------------------
def test_provider_module_does_not_reference_gs_geography():
    mod = importlib.import_module("app.core.optional.providers.ocr")
    source_file = getattr(mod, "__file__", "") or ""
    assert "geography" not in source_file.lower()
    import inspect

    source = inspect.getsource(mod)
    assert "geography" not in source.lower()
    assert "/upsc/geography" not in source.lower()
