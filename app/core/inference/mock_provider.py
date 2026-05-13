from .contracts import IInferenceProvider, InferenceRequest, InferenceResponse

class MockProvider(IInferenceProvider):
    def generate(self, request: InferenceRequest) -> InferenceResponse:
        return InferenceResponse(
            text="[MOCK RESPONSE] This is a simulated AI response for architectural testing.",
            provider="mock/internal"
        )

    async def generate_async(self, request: InferenceRequest) -> InferenceResponse:
        return self.generate(request)
