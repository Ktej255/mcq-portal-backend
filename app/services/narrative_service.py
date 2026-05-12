import google.generativeai as genai
from app.core.config import settings
from typing import Dict, Any

def generate_performance_narrative(report_data: Dict[str, Any], behavioral_data: Dict[str, Any]) -> str:
    if not settings.GOOGLE_API_KEY:
        return "AI Narrative generation is currently disabled (API Key missing)."

    genai.configure(api_key=settings.GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash')

    prompt = f"""
    You are an expert cognitive performance coach for competitive exams.
    Analyze the following exam data and provide a personalized, actionable, and empathetically framed narrative.

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

    TOPIC PERFORMANCE:
    {report_data.get('topic_wise_analysis')}

    REQUIREMENTS:
    1. Start with a warm, encouraging assessment of their performance.
    2. Identify their top 2 cognitive traits (e.g., 'Careful Deliberator', 'Intuitive Speedster').
    3. Explain ONE specific behavioral risk (e.g., 'Panic answering at the end').
    4. Provide a 3-step 'Roadmap to Mastery' based on the topic analysis.
    5. Keep it under 250 words. Use Markdown for formatting.
    """

    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Narrative Generation Error: {str(e)}")
        return "Our AI coach is currently processing a high volume of reports. Please check back in a few minutes for your personalized insight."
