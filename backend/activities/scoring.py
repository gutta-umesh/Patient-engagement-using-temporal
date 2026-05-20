"""
Symptom Scoring Activity — LLM-powered sentiment + PHQ-2 style scoring.

In production: sends free-text patient response to an LLM for sentiment analysis
and PHQ-2 style screening, returning a 0-3 risk score.
Mock: analyses keywords in the text or uses numeric answers.
"""

import random
import re

from temporalio import activity

from shared.constants import RISK_LOW_MAX, RISK_MODERATE, RISK_HIGH_MIN
from shared.models import SurveyResponse, SymptomScore


# ── Keyword-based mock LLM scoring ──────────────────────────────────────────
HIGH_RISK_KEYWORDS = [
    "severe", "unbearable", "emergency", "chest pain", "can't breathe",
    "blood", "bleeding", "dizzy", "fainted", "worst", "terrible",
    "suicidal", "hopeless", "crisis", "fever", "infection",
]

MODERATE_RISK_KEYWORDS = [
    "tired", "fatigue", "headache", "nausea", "moderate", "uncomfortable",
    "worried", "anxious", "trouble sleeping", "sore", "aching", "stiff",
    "swollen", "swelling", "weak", "difficulty",
]

LOW_RISK_KEYWORDS = [
    "good", "fine", "better", "great", "improving", "well", "okay",
    "mild", "slight", "minor", "comfortable", "recovering", "positive",
]


@activity.defn(name="scoreSymptoms")
async def score_symptoms(response: SurveyResponse) -> SymptomScore:
    """
    Score patient symptoms using mock LLM sentiment + PHQ-2 style analysis.

    Supports two modes:
    1. Numeric answers: max(answers) determines severity tier
    2. Free-text: keyword analysis simulates LLM scoring (0-3 scale)

    Risk mapping:
      - 0-1 → low risk → send wellness content
      - 2   → moderate → schedule callback
      - 3+  → high risk → escalate to care team
    """
    # Determine score from numeric answers
    max_score = max(response.answers) if response.answers else 0

    # Generate LLM-style reasoning
    if max_score <= RISK_LOW_MAX:
        risk_level = "low"
        recommendation = "wellness_content"
        reasoning = (
            "Patient responses indicate minimal symptom burden. "
            "PHQ-2 equivalent score falls within normal range. "
            "Sentiment analysis shows positive recovery outlook."
        )
    elif max_score == RISK_MODERATE:
        risk_level = "moderate"
        recommendation = "schedule_callback"
        reasoning = (
            "Patient reports moderate symptoms requiring clinical attention. "
            "PHQ-2 screening suggests possible adjustment disorder. "
            "Recommend nurse callback within 24 hours for assessment."
        )
    else:
        risk_level = "high"
        recommendation = "escalate"
        reasoning = (
            "Patient reports severe symptoms indicating potential complications. "
            "PHQ-2 score exceeds clinical threshold. "
            "Immediate care team intervention recommended."
        )

    result = SymptomScore(
        score=max_score,
        risk_level=risk_level,
        recommendation=recommendation,
        reasoning=reasoning,
    )

    activity.logger.info(
        f"[AI/LLM] Symptom scoring complete — "
        f"Score: {result.score}/3 | "
        f"Risk: {result.risk_level} | "
        f"Recommendation: {result.recommendation}"
    )
    activity.logger.info(f"[AI/LLM] Reasoning: {reasoning}")
    return result


@activity.defn(name="scoreFreeText")
async def score_free_text(text: str) -> SymptomScore:
    """
    Score free-text patient response using mock LLM analysis.
    Simulates sentiment analysis + PHQ-2 style screening.
    
    Used when the survey signal contains free-text rather than numeric answers.
    """
    text_lower = text.lower()

    # Count keyword matches to simulate LLM confidence
    high_matches = sum(1 for kw in HIGH_RISK_KEYWORDS if kw in text_lower)
    mod_matches = sum(1 for kw in MODERATE_RISK_KEYWORDS if kw in text_lower)
    low_matches = sum(1 for kw in LOW_RISK_KEYWORDS if kw in text_lower)

    activity.logger.info(
        f"[AI/LLM] Free-text analysis — "
        f"high_risk_signals={high_matches}, "
        f"moderate_signals={mod_matches}, "
        f"low_risk_signals={low_matches}"
    )

    if high_matches >= 1:
        score = 3
        risk_level = "high"
        recommendation = "escalate"
        reasoning = (
            f"Free-text sentiment analysis detected {high_matches} high-risk indicator(s). "
            f"Patient language suggests acute distress or complications. "
            f"PHQ-2 equivalent score: 3 (above clinical threshold)."
        )
    elif mod_matches >= 2 or (mod_matches >= 1 and low_matches == 0):
        score = 2
        risk_level = "moderate"
        recommendation = "schedule_callback"
        reasoning = (
            f"Free-text analysis found {mod_matches} moderate concern indicator(s). "
            f"Patient reports symptoms requiring clinical follow-up. "
            f"PHQ-2 equivalent score: 2 (borderline)."
        )
    elif low_matches >= 1:
        score = random.choice([0, 1])
        risk_level = "low"
        recommendation = "wellness_content"
        reasoning = (
            f"Positive sentiment detected with {low_matches} wellness indicator(s). "
            f"Patient appears to be recovering well. "
            f"PHQ-2 equivalent score: {score} (normal range)."
        )
    else:
        # Ambiguous — default to moderate for safety
        score = random.choice([1, 2])
        risk_level = "moderate" if score == 2 else "low"
        recommendation = "schedule_callback" if score == 2 else "wellness_content"
        reasoning = (
            f"Free-text response is ambiguous. "
            f"Unable to determine clear sentiment. "
            f"Assigning conservative score of {score} for safety."
        )

    result = SymptomScore(
        score=score,
        risk_level=risk_level,
        recommendation=recommendation,
        reasoning=reasoning,
    )

    activity.logger.info(
        f"[AI/LLM] Free-text scoring complete — "
        f"Score: {result.score}/3 | Risk: {result.risk_level} | "
        f"Recommendation: {result.recommendation}"
    )
    return result
