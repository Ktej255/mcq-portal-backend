from app.core.config import settings
from typing import Dict, Any

try:
    import google.generativeai as genai
except ImportError:
    genai = None

def generate_rule_based_narrative(report_data: Dict[str, Any], behavioral_data: Dict[str, Any]) -> str:
    """Heuristic fallback when AI is unavailable - providing high-fidelity structured analysis."""
    accuracy = report_data.get('accuracy', 0)
    guessing = behavioral_data.get('guessing_rate', 0)
    hesitation = behavioral_data.get('hesitation_index', 0)
    overconfidence = behavioral_data.get('overconfidence_rate', 0)
    
    narrative = "## Educational Intelligence Dossier\n\n"
    
    # 1. Executive Summary
    narrative += "### 1. Executive Summary\n"
    if accuracy >= 80:
        narrative += "Outstanding performance. Your cognitive retrieval is both precise and stable. You are operating at the 'Mastery' level for this subject domain.\n\n"
    elif accuracy >= 60:
        narrative += "Proficient performance. You have a strong grasp of core concepts, though some friction exists in higher-order application or complex reasoning chains.\n\n"
    elif accuracy >= 40:
        narrative += "Developing competency. There is significant 'Knowledge Fragmentation' visible—where you understand parts of a concept but fail during the final integration step.\n\n"
    else:
        narrative += "Emerging stage. Current results indicate foundational conceptual bottlenecks. Priority should be on rebuilding first principles before attempting high-speed drills.\n\n"
        
    if guessing > 25:
        narrative += "**Behavioral Pattern:** High volatility in answer selection (Guessing Rate: " + f"{guessing:.1f}%" + "). This may indicate a tendency to attempt questions without sufficient elimination evidence.\n\n"
    
    if hesitation > 30:
        narrative += "**Behavioral Pattern:** Significant time-spend on correct answers (Hesitation Index: " + f"{hesitation:.1f}%" + "). This suggests that while your knowledge is present, it is not yet 'fluent'. Work on speed drills to build automaticity.\n\n"

    narrative += "### Next Steps\n1. Review the 'Confidence Matrix' to identify blind spots.\n2. Focus on the lowest accuracy topic shown in your mastery map.\n3. Attempt a similar batch tomorrow to measure recovery stability."
    
    return narrative

def generate_performance_narrative(report_data: Dict[str, Any], behavioral_data: Dict[str, Any]) -> str:
    if not settings.GOOGLE_API_KEY or genai is None:
        return generate_rule_based_narrative(report_data, behavioral_data)

    genai.configure(api_key=settings.GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

    prompt = f"""
    You are an expert cognitive performance coach for competitive exams.
    Analyze the following exam data and provide a personalized, actionable, and empathetically framed narrative.
    You must distinguish evidence from inference and include uncertainty qualifiers.

    SCORES:
    - Total Score: {report_data.get('total_score')}
    - Accuracy: {report_data.get('accuracy')}%
    - Correct: {report_data.get('correct_count')}
    - Incorrect: {report_data.get('incorrect_count')}
    - Skipped: {report_data.get('unattempted_count')}

    BEHAVIORAL SIGNALS:
    - Guessing Rate: {behavioral_data.get('guessing_rate', 0):.1f}%
    - Overconfidence Rate: {behavioral_data.get('overconfidence_rate', 0):.1f}%
    - Hesitation Index: {behavioral_data.get('hesitation_index', 0):.1f}%
    - Behavioral Data Quality: {behavioral_data.get('behavioral_data_quality', {}).get('score', 0):.2f}
    - Narrative Safety Guidance: {behavioral_data.get('inference_reliability', {}).get('narrative_safety', {}).get('uncertainty_qualifier', 'Use cautious language.')}

    TOPIC PERFORMANCE:
    {report_data.get('topic_wise_analysis')}

    REQUIREMENTS:
    1. Start with a warm, encouraging assessment of their performance.
    2. Identify up to 2 evidence-backed learning patterns, not fixed traits.
    3. Explain ONE possible behavioral risk using phrases like "may indicate" or "is consistent with".
    4. Provide a 3-step 'Roadmap to Mastery' based on the topic analysis.
    5. Keep it under 250 words. Use Markdown for formatting.
    6. Do not diagnose, overclaim, or present speculation as fact.
    """

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Narrative Generation Error: {str(e)}")
        # Fallback to heuristic if API fails
        return generate_rule_based_narrative(report_data, behavioral_data)
