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
