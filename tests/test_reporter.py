"""Tests for core/reporter.py — prompt construction and narrative generation."""
from unittest.mock import MagicMock, patch

from chesslens.core.patterns import ColorStats, OpeningStats, PatternReport
from chesslens.core.reporter import _build_prompt, generate_narrative


def _make_report(**overrides) -> PatternReport:
    base = PatternReport(
        username="testuser",
        month="2026-05",
        total_games=30,
        wins=15,
        losses=12,
        draws=3,
        win_rate=0.5,
        as_white=ColorStats(games=15, wins=8, losses=6, draws=1, win_rate=0.533),
        as_black=ColorStats(games=15, wins=7, losses=6, draws=2, win_rate=0.467),
        top_openings=[
            OpeningStats("Sicilian Defense", "B20", 10, 6, 3, 1, 0.6),
            OpeningStats("French Defense", "C00", 5, 2, 3, 0, 0.4),
        ],
        worst_opening=OpeningStats("French Defense", "C00", 5, 2, 3, 0, 0.4),
        timeout_count=6,
        timeout_rate=0.2,
        avg_timeout_ply=60.5,
        avg_accuracy=72.5,
        avg_centipawn_loss=45.2,
        blunders_per_game=1.3,
        weekly_performance=[],
        main_pain="timeout",
    )
    for k, v in overrides.items():
        object.__setattr__(base, k, v)
    return base


def test_prompt_contains_username():
    report = _make_report()
    prompt = _build_prompt(report)
    assert "testuser" in prompt


def test_prompt_contains_month():
    report = _make_report()
    prompt = _build_prompt(report)
    assert "2026-05" in prompt


def test_prompt_contains_main_pain():
    report = _make_report(main_pain="opening")
    prompt = _build_prompt(report)
    assert "opening" in prompt.lower()


def test_prompt_handles_missing_accuracy():
    report = _make_report(avg_accuracy=None, avg_centipawn_loss=None, blunders_per_game=None)
    prompt = _build_prompt(report)
    assert "N/A" in prompt


def test_prompt_handles_no_worst_opening():
    report = _make_report(worst_opening=None)
    prompt = _build_prompt(report)
    assert "N/A" in prompt


def test_generate_narrative_calls_litellm():
    report = _make_report()
    mock_response = MagicMock()
    mock_response.choices[0].message.content = "  Great month!  "

    with patch("chesslens.core.reporter.completion", return_value=mock_response) as mock_completion:
        result = generate_narrative(report)

    mock_completion.assert_called_once()
    call_kwargs = mock_completion.call_args.kwargs
    assert call_kwargs["messages"][0]["role"] == "user"
    assert "testuser" in call_kwargs["messages"][0]["content"]
    assert result == "Great month!"  # stripped
