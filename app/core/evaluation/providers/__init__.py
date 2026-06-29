"""Provider implementations for the shared evaluation core.

Exposes the answer-evaluation provider abstraction + factory. The provider
layer is subject-neutral and imports nothing from GS or Optional domains.
"""
from app.core.evaluation.providers.evaluation import (
    EvaluationProvider,
    GatewayEvaluationProvider,
    MockEvaluationProvider,
    get_evaluation_provider,
)
from app.core.evaluation.providers.ocr import (
    GeminiVisionOcrProvider,
    MockOcrProvider,
    OcrNotConfiguredError,
    OcrProvider,
    OcrResult,
    get_ocr_provider,
)

__all__ = [
    "EvaluationProvider",
    "MockEvaluationProvider",
    "GatewayEvaluationProvider",
    "get_evaluation_provider",
    "OcrProvider",
    "OcrResult",
    "OcrNotConfiguredError",
    "MockOcrProvider",
    "GeminiVisionOcrProvider",
    "get_ocr_provider",
]
