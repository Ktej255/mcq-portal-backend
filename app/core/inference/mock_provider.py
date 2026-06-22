import hashlib
import json

from .contracts import IInferenceProvider, InferenceRequest, InferenceResponse


class MockProvider(IInferenceProvider):
    def generate(self, request: InferenceRequest) -> InferenceResponse:
        if request.audio is not None:
            # Deterministic multimodal (audio) response — used to exercise the
            # audio gateway path offline (e.g. speech-to-text) without a model
            # or credentials. Same audio bytes always yield the same output.
            # The payload is JSON so the STT provider's parser can be tested
            # end-to-end against a real (structured) response shape.
            digest = hashlib.sha256(request.audio or b"").hexdigest()[:8]
            transcript = (
                f"[MOCK GEMINI STT {digest}] simulated spoken transcription"
            )
            payload = {
                "text": transcript,
                "confidence": 0.9,
                "segments": [
                    {"text": transcript, "start": 0.0, "end": 1.0, "confidence": 0.9},
                ],
            }
            return InferenceResponse(
                text=json.dumps(payload),
                provider="mock/internal-audio",
            )

        if request.image is not None:
            # Deterministic multimodal (vision) response — used to exercise the
            # vision gateway path offline (e.g. handwriting OCR) without a model
            # or credentials. Same image bytes always yield the same output.
            # The payload is JSON so the OCR provider's parser can be tested
            # end-to-end against a real (structured) response shape.
            digest = hashlib.sha256(request.image or b"").hexdigest()[:8]
            transcription = (
                f"[MOCK VISION OCR {digest}] simulated handwritten transcription"
            )
            payload = {
                "text": transcription,
                "confidence": 0.9,
                "blocks": [
                    {"text": transcription, "confidence": 0.9},
                ],
            }
            return InferenceResponse(
                text=json.dumps(payload),
                provider="mock/internal-vision",
            )

        return InferenceResponse(
            text="[MOCK RESPONSE] This is a simulated AI response for architectural testing.",
            provider="mock/internal"
        )

    async def generate_async(self, request: InferenceRequest) -> InferenceResponse:
        return self.generate(request)
