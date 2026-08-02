import base64
import json
import sys

import pytest

from quordle.dashboard import (
    build_html,
    chart_avg_guess_trend,
    chart_board_difficulty,
    chart_boards_over_time,
    chart_cumulative_solves,
    chart_guess_distribution,
    chart_solve_position,
    load,
    main,
    save_png,
    summary,
)

# A small, schema-valid pair of games: one win, one loss (board 4 unsolved),
# used across the chart/build_html/summary tests below so we exercise real
# aggregation logic (multiple boards, a mix of solved/unsolved, a mix of
# won/lost games) rather than a single trivial game.
GAME_WIN = {
    "seq": 1,
    "date": "2026-08-01",
    "mode": "daily",
    "guesses": ["SLATE", "CURIO", "OMEGA", "SMOCK", "BIRCH", "EERIE"],
    "totalGuessesUsed": 6,
    "maxGuesses": 9,
    "boardsSolved": 4,
    "won": True,
    "words": [
        {"board": 1, "answer": "OMEGA", "solvedOnGuess": 3},
        {"board": 2, "answer": "BIRCH", "solvedOnGuess": 5},
        {"board": 3, "answer": "SMOCK", "solvedOnGuess": 4},
        {"board": 4, "answer": "EERIE", "solvedOnGuess": 6},
    ],
}

GAME_LOSS = {
    "seq": 2,
    "date": "2026-08-01",
    "mode": "practice",
    "guesses": ["SLATE", "CURIO", "STUCK", "CREDO", "CREWS", "PLANK", "CRESS", "TOTEM", "DINGY"],
    "totalGuessesUsed": 9,
    "maxGuesses": 9,
    "boardsSolved": 3,
    "won": False,
    "words": [
        {"board": 1, "answer": "CRESS", "solvedOnGuess": 7},
        {"board": 2, "answer": "STUCK", "solvedOnGuess": 3},
        {"board": 3, "answer": "PLANK", "solvedOnGuess": 6},
        {"board": 4, "answer": "CREDO", "solvedOnGuess": 0},
    ],
}

SAMPLE_GAMES = [GAME_WIN, GAME_LOSS]


@pytest.fixture(scope="module")
def games():
    return SAMPLE_GAMES


@pytest.fixture(scope="module")
def charts(games):
    """Compute all six charts once and reuse — matplotlib rendering isn't free."""
    return {
        "guess_dist": chart_guess_distribution(games),
        "solve_pos": chart_solve_position(games),
        "boards_time": chart_boards_over_time(games),
        "avg_trend": chart_avg_guess_trend(games),
        "cum_solves": chart_cumulative_solves(games),
        "board_diff": chart_board_difficulty(games),
    }


def test_summary_counts_wins_and_boards():
    games = [
        {
            "seq": 1,
            "won": True,
            "totalGuessesUsed": 6,
            "boardsSolved": 4,
            "maxGuesses": 9,
            "words": [{"board": b, "answer": "CRANE", "solvedOnGuess": 3} for b in range(1, 5)],
        }
    ]
    stats = summary(games)
    assert stats["games"] == 1
    assert stats["win_rate"] == "100%"
    assert stats["board_rate"] == "100%"


def test_summary_handles_a_mix_of_wins_and_losses(games):
    stats = summary(games)
    assert stats["games"] == 2
    assert stats["win_rate"] == "50%"
    assert stats["board_rate"] == "88%"  # 7 of 8 boards solved
    assert stats["avg_guesses"] == "6.0"  # only the win counts
    assert stats["best"] == 6


def test_summary_handles_no_games():
    stats = summary([])
    assert stats == {
        "games": 0,
        "win_rate": "0%",
        "board_rate": "0%",
        "avg_guesses": "—",
        "best": "—",
    }


def test_load_round_trips_and_sorts_by_seq(tmp_path):
    path = tmp_path / "games.jsonl"
    # Written out of seq order, with a blank line thrown in, to check both
    # blank-line skipping and the post-load sort by seq.
    path.write_text(
        json.dumps(GAME_LOSS) + "\n" + "\n" + json.dumps(GAME_WIN) + "\n",
        encoding="utf-8",
    )
    loaded = load(str(path))
    assert [g["seq"] for g in loaded] == [1, 2]
    assert loaded[0] == GAME_WIN
    assert loaded[1] == GAME_LOSS


def test_load_reads_the_committed_sample_file():
    games = load("data/quordle_games.sample.jsonl")
    assert len(games) == 2
    assert games[0]["seq"] == 1
    assert games[1]["seq"] == 2


def test_save_png_writes_decoded_bytes(tmp_path):
    raw = b"not-really-a-png-but-bytes-are-bytes"
    b64 = base64.b64encode(raw).decode("ascii")
    out = tmp_path / "chart.png"
    save_png(b64, str(out))
    assert out.read_bytes() == raw


def test_chart_guess_distribution_returns_base64_png(charts):
    result = charts["guess_dist"]
    assert isinstance(result, str)
    assert len(result) > 100


def test_chart_solve_position_returns_base64_png(charts):
    result = charts["solve_pos"]
    assert isinstance(result, str)
    assert len(result) > 100


def test_chart_boards_over_time_returns_base64_png(charts):
    result = charts["boards_time"]
    assert isinstance(result, str)
    assert len(result) > 100


def test_chart_avg_guess_trend_returns_base64_png(charts):
    result = charts["avg_trend"]
    assert isinstance(result, str)
    assert len(result) > 100


def test_chart_cumulative_solves_returns_base64_png(charts):
    result = charts["cum_solves"]
    assert isinstance(result, str)
    assert len(result) > 100


def test_chart_board_difficulty_returns_base64_png(charts):
    result = charts["board_diff"]
    assert isinstance(result, str)
    assert len(result) > 100


def test_build_html_contains_expected_markers(games, charts):
    stats = summary(games)
    html = build_html(games, charts, stats)
    assert isinstance(html, str)
    assert "<html" in html
    assert stats["win_rate"] in html
    assert "<img" in html
    assert "Quordle Stats" in html


def _write_games_jsonl(path, games):
    path.write_text("\n".join(json.dumps(g) for g in games) + "\n", encoding="utf-8")


def test_main_writes_dashboard_and_png_dir(tmp_path, monkeypatch, capsys):
    games_path = tmp_path / "games.jsonl"
    _write_games_jsonl(games_path, SAMPLE_GAMES)
    out_path = tmp_path / "dashboard.html"
    png_dir = tmp_path / "charts"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "quordle-stats",
            str(games_path),
            "-o",
            str(out_path),
            "--png-dir",
            str(png_dir),
        ],
    )

    main()

    assert out_path.exists()
    assert "<html" in out_path.read_text(encoding="utf-8")
    assert png_dir.is_dir()
    assert (png_dir / "guess_dist.png").exists()
    assert (png_dir / "board_diff.png").exists()

    captured = capsys.readouterr()
    assert "Wrote" in captured.out
    assert "Wrote PNGs" in captured.out


def test_main_writes_dashboard_without_png_dir(tmp_path, monkeypatch, capsys):
    games_path = tmp_path / "games.jsonl"
    _write_games_jsonl(games_path, SAMPLE_GAMES)
    out_path = tmp_path / "dashboard.html"

    monkeypatch.setattr(
        sys,
        "argv",
        ["quordle-stats", str(games_path), "-o", str(out_path)],
    )

    main()

    assert out_path.exists()
    captured = capsys.readouterr()
    assert "Wrote" in captured.out
    assert "Wrote PNGs" not in captured.out


def test_main_exits_when_no_games_found(tmp_path, monkeypatch):
    empty_path = tmp_path / "empty.jsonl"
    empty_path.write_text("", encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["quordle-stats", str(empty_path)])

    with pytest.raises(SystemExit):
        main()
