from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, List
from pydantic import BaseModel

class InferenceRequest(BaseModel):
    prompt: str
    system_instruction: Optional[str] = None
    temperature: float = 0.7
    max_tokens: Optional[int] = None
    response_mime_type: Optional[str] = "text/plain"

class InferenceResponse(BaseModel):
    text: str
    raw_response: Any = None
    usage_metadata: Dict[str, int] = {}
    provider: str

class IInferenceProvider(ABC):
    @abstractmethod
    def generate(self, request: InferenceRequest) -> InferenceResponse:
        pass

    @abstractmethod
    async def generate_async(self, request: InferenceRequest) -> InferenceResponse:
        pass
