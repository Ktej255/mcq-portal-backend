import google.generativeai as genai
from .contracts import IInferenceProvider, InferenceRequest, InferenceResponse
from app.core.config import settings

class GeminiProvider(IInferenceProvider):
    def __init__(self, model_name: str = "gemini-1.5-flash"):
        self.model_name = model_name
        genai.configure(api_key=settings.GOOGLE_API_KEY)
        self.model = genai.GenerativeModel(model_name)

    def generate(self, request: InferenceRequest) -> InferenceResponse:
        # Note: In a production gateway, we would map InferenceRequest fields to Gemini fields
        if request.audio is not None:
            # Multimodal (audio) path — e.g. speech-to-text. Gemini 1.5 accepts
            # inline audio blobs alongside a text prompt. This branch is only
            # ever taken when a caller supplies ``audio``; text-only and vision
            # calls fall through to the unchanged paths below (backward-compatible).
            generation_config = {"temperature": request.temperature}
            if request.response_mime_type and request.response_mime_type != "text/plain":
                generation_config["response_mime_type"] = request.response_mime_type
            if request.max_tokens:
                generation_config["max_output_tokens"] = request.max_tokens
            parts = [
                request.prompt,
                {
                    "mime_type": request.audio_mime_type or "audio/wav",
                    "data": request.audio,
                },
            ]
            response = self.model.generate_content(
                parts, generation_config=generation_config
            )
            return InferenceResponse(
                text=response.text,
                raw_response=response,
                provider="google/gemini-audio",
            )

        if request.image is not None:
            # Multimodal (vision) path — e.g. handwriting OCR. The image is sent
            # as an inline blob part alongside the text prompt. This branch is
            # only ever taken when a caller supplies ``image``; text-only calls
            # fall through to the unchanged path below (backward-compatible).
            generation_config = {"temperature": request.temperature}
            if request.response_mime_type and request.response_mime_type != "text/plain":
                generation_config["response_mime_type"] = request.response_mime_type
            if request.max_tokens:
                generation_config["max_output_tokens"] = request.max_tokens
            parts = [
                request.prompt,
                {
                    "mime_type": request.image_mime_type or "image/png",
                    "data": request.image,
                },
            ]
            response = self.model.generate_content(
                parts, generation_config=generation_config
            )
            return InferenceResponse(
                text=response.text,
                raw_response=response,
                provider="google/gemini-vision",
            )

        # Text-only path (unchanged).
        response = self.model.generate_content(request.prompt)
        return InferenceResponse(
            text=response.text,
            raw_response=response,
            provider="google/gemini"
        )

    async def generate_async(self, request: InferenceRequest) -> InferenceResponse:
        # Gemini Python SDK doesn't have a direct async generate_content in standard sync client
        # but for this architectural shell, we wrap it or use the async client if available.
        # For now, we'll implement the sync-wrapper pattern to maintain the interface.
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.generate, request)
