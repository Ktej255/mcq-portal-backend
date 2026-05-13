from typing import Dict, Type
from .contracts import IInferenceProvider, InferenceRequest, InferenceResponse
from .gemini_provider import GeminiProvider
from .mock_provider import MockProvider

from app.core.observability.tracer import trace_execution

class InferenceGateway:
    _providers: Dict[str, IInferenceProvider] = {}
    _default_provider_name: str = "gemini"

    @classmethod
    def get_provider(cls, name: str = None) -> IInferenceProvider:
        name = name or cls._default_provider_name
        if name not in cls._providers:
            if name == "gemini":
                cls._providers[name] = GeminiProvider()
            elif name == "mock":
                cls._providers[name] = MockProvider()
            else:
                raise ValueError(f"Provider {name} not found")
        return cls._providers[name]

    @classmethod
    def generate(cls, prompt: str, provider: str = None, **kwargs) -> InferenceResponse:
        provider_name = provider or cls._default_provider_name
        with trace_execution(module_name="core.inference", function_name=f"generate:{provider_name}") as trace:
            trace.input_payload = {"prompt": prompt[:100] + "...", "provider": provider_name}
            request = InferenceRequest(prompt=prompt, **kwargs)
            response = cls.get_provider(provider_name).generate(request)
            trace.output_payload = {"status": "success", "tokens": getattr(response, 'usage', {})}
            return response

    @classmethod
    async def generate_async(cls, prompt: str, provider: str = None, **kwargs) -> InferenceResponse:
        provider_name = provider or cls._default_provider_name
        with trace_execution(module_name="core.inference", function_name=f"generate_async:{provider_name}") as trace:
            trace.input_payload = {"prompt": prompt[:100] + "...", "provider": provider_name}
            request = InferenceRequest(prompt=prompt, **kwargs)
            response = await cls.get_provider(provider_name).generate_async(request)
            trace.output_payload = {"status": "success", "tokens": getattr(response, 'usage', {})}
            return response

# Singleton-like access
inference_gateway = InferenceGateway()
