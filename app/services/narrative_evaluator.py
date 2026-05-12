from app.core.config import settings
from app.schemas.cognitive import NarrativeEvaluation
from typing import Dict, Any

try:
    import google.generativeai as genai
except ImportError:
    genai = None

class NarrativeEvaluator:
    def evaluate(self, narrative: str, report_data: Dict[str, Any], behavioral_data: Dict[str, Any]) -> NarrativeEvaluation:
        reliability = behavioral_data.get("inference_reliability", {})
        narrative_safety = reliability.get("narrative_safety", {})
        if not settings.GOOGLE_API_KEY or genai is None:
            return NarrativeEvaluation(
                narrative_id="N/A",
                hallucination_score=0.0,
                relevance_score=0.0,
                contradiction_detected=False,
                uncertainty_score=1 - behavioral_data.get("behavioral_data_quality", {}).get("score", 0),
                requires_human_review=narrative_safety.get("requires_human_review", False)
            )

        genai.configure(api_key=settings.GOOGLE_API_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')

        eval_prompt = f"""
        Analyze the following AI-generated exam narrative for scientific accuracy and logical consistency.
        
        NARRATIVE:
        {narrative}
        
        GROUND TRUTH DATA:
        - Accuracy: {report_data.get('accuracy')}%
        - Guessing Rate: {behavioral_data.get('guessing_rate', 0):.1f}%
        - Hesitation Index: {behavioral_data.get('hesitation_index', 0):.1f}%
        - Behavioral Data Quality: {behavioral_data.get('behavioral_data_quality', {}).get('score', 0):.2f}
        - Contradiction Score: {reliability.get('contradictions', {}).get('contradiction_score', 0):.2f}
        
        TASK:
        Rate the narrative on a scale of 0 to 1 for:
        1. Hallucination (Does it claim things NOT in the data?)
        2. Relevance (Is it actually helpful or generic?)
        3. Contradiction (Does it say 'great job' but then 'you failed'?)
        4. Uncertainty handling (Does it avoid overclaiming?)
        
        Format your response as a JSON object with:
        {{
            "hallucination_score": float,
            "relevance_score": float,
            "contradiction_detected": boolean,
            "brief_reason": string
        }}
        """

        try:
            response = model.generate_content(eval_prompt)
            # Simplified parsing for the example
            import json
            import re
            match = re.search(r'\{.*\}', response.text, re.DOTALL)
            if match:
                eval_data = json.loads(match.group())
                return NarrativeEvaluation(
                    narrative_id="GEN-001", # Placeholder
                    hallucination_score=eval_data.get('hallucination_score', 0),
                    relevance_score=eval_data.get('relevance_score', 0),
                    contradiction_detected=eval_data.get('contradiction_detected', False),
                    uncertainty_score=eval_data.get('uncertainty_score', 0),
                    requires_human_review=narrative_safety.get("requires_human_review", False),
                    expert_comments=eval_data.get('brief_reason')
                )
        except Exception as e:
            print(f"Narrative Evaluation Error: {str(e)}")
        
        return NarrativeEvaluation(
            narrative_id="ERR-001",
            hallucination_score=0.5,
            relevance_score=0.5,
            contradiction_detected=False,
            uncertainty_score=0.5,
            requires_human_review=narrative_safety.get("requires_human_review", False)
        )

narrative_evaluator = NarrativeEvaluator()
