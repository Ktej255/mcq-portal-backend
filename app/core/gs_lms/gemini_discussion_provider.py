"""Gemini AI Response Provider for the GS LMS Discussion Engine.

Bridges the AIResponseProvider protocol with Google's Generative AI SDK.
Falls back to MockAIResponseProvider on any SDK failure to ensure the
discussion flow is never blocked.

Requirements traced: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7
"""

from __future__ import annotations

import logging
import os

import google.generativeai as genai

from app.core.gs_lms.discussion import (
    AIResponseProvider,
    MockAIResponseProvider,
    set_default_provider,
)

logger = logging.getLogger(__name__)

_SYSTEM_INSTRUCTION = (
    "You are a Socratic tutor for UPSC Geography. Given the topic, prior conversation, "
    "and the student's latest message, ask a probing counter-question that tests depth "
    "of understanding. Keep responses concise (2-3 sentences max)."
)


class GeminiAIResponseProvider:
    """Concrete AIResponseProvider backed by Google Generative AI (Gemini).

    Implements the AIResponseProvider protocol defined in
    app.core.gs_lms.discussion. On SDK failure, delegates to the
    MockAIResponseProvider and logs the error.
    """

    def __init__(self, model_name: str = "gemini-1.5-flash"):
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        if not api_key:
            raise ValueError("GOOGLE_API_KEY is required for GeminiAIResponseProvider")
        genai.configure(api_key=api_key)
        self._model = genai.GenerativeModel(
            model_name,
            system_instruction=_SYSTEM_INSTRUCTION,
        )
        self._fallback = MockAIResponseProvider()

    def generate_response(
        self,
        topic_title: str,
        transcript: list[dict],
        student_message: str,
        concepts_missed: list[str] | None = None,
        match_percentage: float | None = None,
    ) -> str:
        """Generate a Gemini-powered counter-question, falling back to mock on error.

        When concepts_missed is provided, the prompt is enhanced to generate
        Socratic questions specifically targeting those missed concepts (R2.6).
        """
        prompt = self._build_prompt(
            topic_title, transcript, student_message,
            concepts_missed=concepts_missed,
            match_percentage=match_percentage,
        )
        try:
            response = self._model.generate_content(prompt)
            return response.text
        except Exception as exc:
            logger.error(
                "Gemini discussion call failed, falling back to mock: %s", exc
            )
            return self._fallback.generate_response(
                topic_title, transcript, student_message,
                concepts_missed=concepts_missed,
                match_percentage=match_percentage,
            )

    def _build_prompt(
        self,
        topic_title: str,
        transcript: list[dict],
        student_message: str,
        concepts_missed: list[str] | None = None,
        match_percentage: float | None = None,
    ) -> str:
        """Assemble the prompt sent to the Gemini SDK.

        When concepts_missed is provided, appends targeted Socratic guidance
        so the AI asks about specific uncovered concepts.
        """
        lines = [f"Topic: {topic_title}", "", "Conversation so far:"]
        for turn in transcript:
            role = turn.get("role", "unknown").capitalize()
            content = turn.get("content", "")
            lines.append(f"  {role}: {content}")
        lines.append(f"\nStudent's latest message: {student_message}")

        # Enhanced prompt for targeting missed concepts (Requirement 2.6)
        if concepts_missed:
            lines.append(
                f"\n\nThe student has explained some concepts well, but has NOT yet "
                f"covered these key concepts: {', '.join(concepts_missed)}. "
                "Ask a focused Socratic question about ONE of the missed concepts "
                "to guide the student toward explaining it."
            )
            if match_percentage is not None:
                lines.append(
                    f"(Current concept coverage: {match_percentage:.0%}. "
                    "The gate opens at 80%.)"
                )
        else:
            lines.append("\nRespond with a Socratic counter-question:")

        return "\n".join(lines)


def register_discussion_provider() -> None:
    """Wire the real Gemini provider if API key is available.

    Called from app/main.py at startup. If the key is missing or provider
    instantiation fails, the Discussion_Engine retains the MockAIResponseProvider.
    """
    api_key = os.environ.get("GOOGLE_API_KEY", "")
    if not api_key:
        logger.warning(
            "GOOGLE_API_KEY not set — Discussion_Engine retaining MockAIResponseProvider"
        )
        return

    try:
        provider = GeminiAIResponseProvider()
        set_default_provider(provider)
        logger.info("Discussion_Engine: GeminiAIResponseProvider registered")
    except Exception as exc:
        logger.error("Failed to register GeminiAIResponseProvider: %s", exc)
