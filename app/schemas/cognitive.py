from pydantic import BaseModel, Field
from typing import List, Dict, Optional, Any
from datetime import datetime

class CognitiveSignal(BaseModel):
    name: str
    value: float
    confidence: float
    interpretation: str
    signal_confidence: float = 0.0
    metric_version: str = "inference-reliability.v1"
    uncertainty_note: Optional[str] = None

class BehavioralSnapshot(BaseModel):
    guessing_rate: float
    hesitation_index: float
    overconfidence_rate: float
    anxiety_index: float
    signals: List[CognitiveSignal] = []
    behavioral_data_quality: Dict[str, Any] = {}
    inference_reliability: Dict[str, Any] = {}

class TopicMasterySnapshot(BaseModel):
    topic_id: int
    topic_name: str
    mastery_score: float
    evidence_count: int
    last_updated: datetime

class StudentCognitiveProfile(BaseModel):
    user_id: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    behavioral: BehavioralSnapshot
    mastery: List[TopicMasterySnapshot]
    overall_accuracy: float
    learning_velocity: float = 0.0
    
    metadata: Dict[str, Any] = {}

class NarrativeEvaluation(BaseModel):
    narrative_id: str
    hallucination_score: float # 0 to 1
    relevance_score: float
    contradiction_detected: bool
    uncertainty_score: float = 0.0
    requires_human_review: bool = False
    metric_version: str = "inference-reliability.v1"
    expert_validated: bool = False
    expert_comments: Optional[str] = None
