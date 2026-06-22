"""Tests for the inference gateway's optional vision (multimodal) extension
(Task 9.3 prerequisite — extending the previously TEXT-ONLY gateway).

These prove two things:

* Backward-compatibility — the new ``image`` field is optional and defaults to
  ``None``, so every existing text-only call is byte-for-byte unaffected: the
  ``InferenceRequest`` contract still accepts a bare ``prompt`` and the mock
  provider returns the same text response it always has.
* The new vision path — when ``image`` bytes are supplied, the mock provider
  returns a deterministic, structured (JSON) multimodal response, exercising the
  gateway's vision branch offline without a model or credentials.

The real ``GeminiProvider`` vision branch is not exercised here (it needs vision
credentials + network); the mock provider is the deterministic dev/test default.
"""

from __future__ import annotations

import json

from app.core.inference.contracts import InferenceRequest
from app.core.inference.gateway import InferenceGateway
from app.core.inference.mock_provider import MockProvider


# ---------------------------------------------------------------------------
# Backward-compatibility — text-only contract + behaviour unchanged
# ---------------------------------------------------------------------------
def test_request_image_field_is_optional_and_defaults_none():
    # A bare text request still constructs exactly as before.
    req = InferenceRequest(prompt="hello")
    assert req.image is None
    assert req.image_mime_type is None


def test_mock_text_only_response_is_unchanged():
    req = InferenceRequest(prompt="hello")
    resp = MockProvider().generate(req)
    assert resp.provider == "mock/internal"
    assert resp.text.startswith("[MOCK RESPONSE]")


def test_gateway_text_generate_unaffected():
    # The classic text-only gateway call path still works and routes to the
    # text branch (no image) of the mock provider.
    resp = InferenceGateway.generate("hello world", provider="mock")
    assert resp.provider == "mock/internal"
    assert resp.text.startswith("[MOCK RESPONSE]")


# ---------------------------------------------------------------------------
# Vision path — image bytes route to the multimodal branch (mock)
# ---------------------------------------------------------------------------
def test_mock_vision_response_when_image_present():
    req = InferenceRequest(prompt="ocr", image=b"image-bytes", image_mime_type="image/png")
    resp = MockProvider().generate(req)
    assert resp.provider == "mock/internal-vision"
    payload = json.loads(resp.text)
    assert isinstance(payload["text"], str) and payload["text"]
    assert 0.0 <= payload["confidence"] <= 1.0
    assert payload["blocks"] and payload["blocks"][0]["text"]


def test_mock_vision_is_deterministic_for_same_image():
    a = MockProvider().generate(InferenceRequest(prompt="ocr", image=b"same"))
    b = MockProvider().generate(InferenceRequest(prompt="ocr", image=b"same"))
    assert a.text == b.text


def test_mock_vision_distinct_images_differ():
    a = MockProvider().generate(InferenceRequest(prompt="ocr", image=b"img-a"))
    b = MockProvider().generate(InferenceRequest(prompt="ocr", image=b"img-b"))
    assert a.text != b.text


def test_gateway_routes_image_through_to_vision_branch():
    resp = InferenceGateway.generate(
        "ocr",
        provider="mock",
        image=b"image-bytes",
        image_mime_type="image/jpeg",
        response_mime_type="application/json",
    )
    assert resp.provider == "mock/internal-vision"
    payload = json.loads(resp.text)
    assert payload["text"]
