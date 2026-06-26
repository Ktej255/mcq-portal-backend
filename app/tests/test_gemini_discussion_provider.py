"""Tests for GeminiAIResponseProvider prompt building (Task 4.4).

Tests the _build_prompt method to verify Socratic follow-up generation
targets missed concepts when provided.

Requirements traced: 2.6
"""

from __future__ import annotations

import pytest
from unittest.mock import patch, MagicMock

from app.core.gs_lms.gemini_discussion_provider import GeminiAIResponseProvider


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def provider():
    """Create a GeminiAIResponseProvider with a mocked API key."""
    with patch.dict("os.environ", {"GOOGLE_API_KEY": "test-key"}):
        with patch("google.generativeai.configure"):
            with patch("google.generativeai.GenerativeModel"):
                return GeminiAIResponseProvider()


# ---------------------------------------------------------------------------
# Prompt Building Tests — Socratic Follow-ups for Missed Concepts (R2.6)
# ---------------------------------------------------------------------------


class TestBuildPromptWithMissedConcepts:
    """Tests for _build_prompt with concepts_missed targeting (R2.6)."""

    def test_prompt_includes_missed_concepts_when_provided(self, provider):
        """When concepts_missed is non-empty, prompt includes them."""
        prompt = provider._build_prompt(
            topic_title="Plate Tectonics",
            transcript=[],
            student_message="I know about earthquakes.",
            concepts_missed=["continental drift", "seafloor spreading"],
            match_percentage=0.4,
        )

        assert "continental drift" in prompt
        assert "seafloor spreading" in prompt
        assert "NOT yet covered" in prompt
        assert "Socratic" in prompt or "focused" in prompt.lower()

    def test_prompt_includes_match_percentage_when_provided(self, provider):
        """When match_percentage is provided alongside missed concepts, it's shown."""
        prompt = provider._build_prompt(
            topic_title="Geomorphology",
            transcript=[],
            student_message="Rivers form valleys.",
            concepts_missed=["erosion types"],
            match_percentage=0.6,
        )

        assert "60%" in prompt
        assert "80%" in prompt  # gate threshold mentioned

    def test_prompt_without_missed_concepts_uses_general_format(self, provider):
        """When no concepts_missed, prompt uses standard Socratic counter-question format."""
        prompt = provider._build_prompt(
            topic_title="Volcanism",
            transcript=[],
            student_message="Volcanoes erupt lava.",
        )

        assert "Socratic counter-question" in prompt
        assert "NOT yet covered" not in prompt

    def test_prompt_with_empty_missed_concepts_uses_general_format(self, provider):
        """When concepts_missed is empty list, prompt uses standard format."""
        prompt = provider._build_prompt(
            topic_title="Volcanism",
            transcript=[],
            student_message="Volcanoes erupt lava.",
            concepts_missed=[],
            match_percentage=1.0,
        )

        assert "Socratic counter-question" in prompt
        assert "NOT yet covered" not in prompt

    def test_prompt_with_none_missed_concepts_uses_general_format(self, provider):
        """When concepts_missed is None, prompt uses standard format."""
        prompt = provider._build_prompt(
            topic_title="Volcanism",
            transcript=[],
            student_message="Volcanoes erupt lava.",
            concepts_missed=None,
            match_percentage=None,
        )

        assert "Socratic counter-question" in prompt
        assert "NOT yet covered" not in prompt

    def test_prompt_asks_about_one_missed_concept(self, provider):
        """Prompt instructs AI to ask about ONE missed concept at a time."""
        prompt = provider._build_prompt(
            topic_title="Ocean Currents",
            transcript=[],
            student_message="Warm currents flow from equator.",
            concepts_missed=["thermohaline circulation", "Coriolis effect", "upwelling"],
            match_percentage=0.25,
        )

        assert "ONE" in prompt
        assert "thermohaline circulation" in prompt
        assert "Coriolis effect" in prompt
        assert "upwelling" in prompt

    def test_prompt_includes_transcript_context(self, provider):
        """Prompt always includes transcript even when targeting missed concepts."""
        transcript = [
            {"role": "student", "content": "I think plate tectonics is important."},
            {"role": "ai", "content": "Can you explain the mechanism?"},
        ]
        prompt = provider._build_prompt(
            topic_title="Plate Tectonics",
            transcript=transcript,
            student_message="Plates move on the asthenosphere.",
            concepts_missed=["subduction zones"],
            match_percentage=0.6,
        )

        assert "plate tectonics is important" in prompt.lower()
        assert "explain the mechanism" in prompt.lower()
        assert "subduction zones" in prompt
