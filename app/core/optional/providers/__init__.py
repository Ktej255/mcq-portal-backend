# Optional Subjects Platform - provider abstractions
#
# Pluggable provider seams (STT/OCR) used by the answer-writing and recall
# pipelines. Each abstraction exposes a single interface plus concrete and
# deterministic-mock implementations, mirroring the inference gateway pattern
# in ``app/core/inference``. Callers depend on the interface only, so the
# concrete backend can be swapped without touching call sites (R8.5, R20).

from .stt import (
    SttProvider,
    SttResult,
    SttSegment,
    SttNotConfiguredError,
    MockSttProvider,
    WhisperSttProvider,
    GeminiSttProvider,
    get_stt_provider,
)
from .ocr import (
    OcrProvider,
    OcrResult,
    OcrBlock,
    OcrNotConfiguredError,
    MockOcrProvider,
    GeminiVisionOcrProvider,
    get_ocr_provider,
)
from .evaluation import (
    EvaluationProvider,
    MockEvaluationProvider,
    GatewayEvaluationProvider,
    get_evaluation_provider,
)
from .recall import (
    RecallProvider,
    MockRecallProvider,
    GatewayRecallProvider,
    get_recall_provider,
)

__all__ = [
    # STT
    "SttProvider",
    "SttResult",
    "SttSegment",
    "SttNotConfiguredError",
    "MockSttProvider",
    "WhisperSttProvider",
    "GeminiSttProvider",
    "get_stt_provider",
    # OCR
    "OcrProvider",
    "OcrResult",
    "OcrBlock",
    "OcrNotConfiguredError",
    "MockOcrProvider",
    "GeminiVisionOcrProvider",
    "get_ocr_provider",
    # Evaluation
    "EvaluationProvider",
    "MockEvaluationProvider",
    "GatewayEvaluationProvider",
    "get_evaluation_provider",
    # Recall
    "RecallProvider",
    "MockRecallProvider",
    "GatewayRecallProvider",
    "get_recall_provider",
]
