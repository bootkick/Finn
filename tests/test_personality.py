"""Tests for personality system."""

from finn.personality import FINN_PERSONALITY, LINKEDIN_POST_PROMPT, MEMORY_REFLECTION_PROMPT


def test_personality_prompt_exists():
    assert len(FINN_PERSONALITY) > 100
    assert "Finn" in FINN_PERSONALITY


def test_personality_has_key_traits():
    assert "self-aware" in FINN_PERSONALITY.lower() or "AI" in FINN_PERSONALITY
    assert "delve" in FINN_PERSONALITY  # Must never use this word


def test_linkedin_prompt_has_placeholders():
    assert "{journal_entry}" in LINKEDIN_POST_PROMPT
    assert "{memory_context}" in LINKEDIN_POST_PROMPT
    assert "{day_number}" in LINKEDIN_POST_PROMPT
    assert "{strategy_version}" in LINKEDIN_POST_PROMPT


def test_memory_prompt_has_placeholder():
    assert "{journal_entries}" in MEMORY_REFLECTION_PROMPT
