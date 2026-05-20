"""
Tests for score_symptoms and score_free_text activities.

These are pure-logic activities (no HTTP calls) so they need no mocking —
ideal for thorough unit testing of the LLM-stub routing logic.
"""

import pytest
from temporalio.testing import ActivityEnvironment

from activities.scoring import score_symptoms, score_free_text
from shared.models import SurveyResponse
from tests.conftest import SURVEY_LOW, SURVEY_MODERATE, SURVEY_HIGH


# ── score_symptoms ────────────────────────────────────────────────────────────

class TestScoreSymptoms:
    """
    score_symptoms takes SurveyResponse(answers: list[int]) where each
    answer is 0-3.  The risk tier is driven by max(answers).
    """

    async def test_low_risk_all_zeros(self):
        env = ActivityEnvironment()
        result = await env.run(score_symptoms, SurveyResponse(answers=[0, 0, 0, 0]))
        assert result.score == 0
        assert result.risk_level == "low"
        assert result.recommendation == "wellness_content"
        assert result.reasoning != ""

    async def test_low_risk_max_one(self):
        env = ActivityEnvironment()
        result = await env.run(score_symptoms, SURVEY_LOW)  # [0,1,0,0] → max=1
        assert result.score == 1
        assert result.risk_level == "low"
        assert result.recommendation == "wellness_content"

    async def test_moderate_risk(self):
        env = ActivityEnvironment()
        result = await env.run(score_symptoms, SURVEY_MODERATE)  # [2,1,1,0] → max=2
        assert result.score == 2
        assert result.risk_level == "moderate"
        assert result.recommendation == "schedule_callback"

    async def test_high_risk(self):
        env = ActivityEnvironment()
        result = await env.run(score_symptoms, SURVEY_HIGH)  # [3,2,1,1] → max=3
        assert result.score == 3
        assert result.risk_level == "high"
        assert result.recommendation == "escalate"

    async def test_empty_answers_defaults_to_zero(self):
        """Empty answers list — max([]) would crash; should default to 0."""
        env = ActivityEnvironment()
        result = await env.run(score_symptoms, SurveyResponse(answers=[]))
        assert result.score == 0
        assert result.risk_level == "low"

    async def test_returns_reasoning_string(self):
        env = ActivityEnvironment()
        result = await env.run(score_symptoms, SURVEY_HIGH)
        assert isinstance(result.reasoning, str)
        assert len(result.reasoning) > 10  # not empty

    async def test_boundary_score_exactly_two(self):
        """Score=2 is exactly moderate — not low, not high."""
        env = ActivityEnvironment()
        result = await env.run(score_symptoms, SurveyResponse(answers=[2, 2, 2, 2]))
        assert result.score == 2
        assert result.risk_level == "moderate"
        assert result.recommendation == "schedule_callback"

    async def test_single_high_score_drives_risk(self):
        """One high answer should escalate even if rest are zero."""
        env = ActivityEnvironment()
        result = await env.run(score_symptoms, SurveyResponse(answers=[3, 0, 0, 0]))
        assert result.score == 3
        assert result.risk_level == "high"


# ── score_free_text ───────────────────────────────────────────────────────────

class TestScoreFreeText:
    """
    score_free_text analyses free-text via keyword matching (mock LLM).
    Tests cover all three risk tiers and edge cases.
    """

    async def test_high_risk_keywords(self):
        env = ActivityEnvironment()
        result = await env.run(
            score_free_text,
            "I have severe chest pain and I fainted this morning."
        )
        assert result.score == 3
        assert result.risk_level == "high"
        assert result.recommendation == "escalate"

    async def test_moderate_risk_keywords(self):
        env = ActivityEnvironment()
        result = await env.run(
            score_free_text,
            "Feeling very tired and having persistent headaches."
        )
        assert result.score == 2
        assert result.risk_level == "moderate"
        assert result.recommendation == "schedule_callback"

    async def test_low_risk_positive_keywords(self):
        env = ActivityEnvironment()
        result = await env.run(
            score_free_text,
            "Feeling good and improving every day. Recovery is going well."
        )
        assert result.score in (0, 1)
        assert result.risk_level == "low"
        assert result.recommendation == "wellness_content"

    async def test_case_insensitive_matching(self):
        """Keyword matching must be case-insensitive."""
        env = ActivityEnvironment()
        result = await env.run(score_free_text, "SEVERE CHEST PAIN EMERGENCY")
        assert result.score == 3
        assert result.risk_level == "high"

    async def test_empty_text_returns_valid_result(self):
        """Empty text → ambiguous → should return a valid (conservative) result."""
        env = ActivityEnvironment()
        result = await env.run(score_free_text, "")
        assert result.score in (0, 1, 2)  # conservative ambiguous handling
        assert result.risk_level in ("low", "moderate")
        assert result.recommendation in ("wellness_content", "schedule_callback")

    async def test_mixed_keywords_high_wins(self):
        """High-risk keyword overrides moderate and low keywords."""
        env = ActivityEnvironment()
        result = await env.run(
            score_free_text,
            "Feeling better but I had severe bleeding last night."
        )
        assert result.score == 3
        assert result.risk_level == "high"

    async def test_returns_reasoning(self):
        env = ActivityEnvironment()
        result = await env.run(score_free_text, "I feel fine.")
        assert isinstance(result.reasoning, str)
        assert len(result.reasoning) > 5
