import sys

import pytest

from quordle.objectives import (
    ConfigPanel,
    avg_position,
    board_positions,
    compare,
    convex_cost,
    first_position,
    main,
    max_position,
    solved_in_nine,
)

# ---- fixtures ---------------------------------------------------------------

GAME_CLAUDE_WIN = {
    "seq": 1,
    "date": "2026-08-01",
    "mode": "browser",
    "player": "claude",
    "model": "claude-sonnet-5",
    "assist": "none",
    "won": True,
    "totalGuessesUsed": 8,
    "maxGuesses": 9,
    "boardsSolved": 4,
    "words": [
        {"board": 1, "answer": "OMEGA", "solvedOnGuess": 4},
        {"board": 2, "answer": "BIRCH", "solvedOnGuess": 5},
        {"board": 3, "answer": "SMOCK", "solvedOnGuess": 7},
        {"board": 4, "answer": "EERIE", "solvedOnGuess": 8},
    ],
}

GAME_CLAUDE_LOSS = {
    "seq": 2,
    "date": "2026-08-01",
    "mode": "browser",
    "player": "claude",
    "model": "claude-sonnet-5",
    "assist": "none",
    "won": False,
    "totalGuessesUsed": 9,
    "maxGuesses": 9,
    "boardsSolved": 3,
    "words": [
        {"board": 1, "answer": "CRESS", "solvedOnGuess": 7},
        {"board": 2, "answer": "STUCK", "solvedOnGuess": 3},
        {"board": 3, "answer": "PLANK", "solvedOnGuess": 6},
        {"board": 4, "answer": "CREDO", "solvedOnGuess": 0},
    ],
}

GAME_CLAUDE_ENDED_EARLY = {
    "seq": 3,
    "date": "2026-08-01",
    "mode": "browser",
    "player": "claude",
    "model": "claude-sonnet-5",
    "assist": "none",
    "won": False,
    "totalGuessesUsed": 2,
    "maxGuesses": 9,
    "boardsSolved": 0,
    "words": [
        {"board": 1, "answer": "", "solvedOnGuess": 0},
        {"board": 2, "answer": "", "solvedOnGuess": 0},
        {"board": 3, "answer": "", "solvedOnGuess": 0},
        {"board": 4, "answer": "", "solvedOnGuess": 0},
    ],
    "endedEarly": True,
}

GAME_HEURISTIC_WIN = {
    "seq": 4,
    "date": "2026-08-01",
    "mode": "practice",
    "player": "heuristic",
    "won": True,
    "totalGuessesUsed": 6,
    "maxGuesses": 9,
    "boardsSolved": 4,
    "words": [
        {"board": 1, "answer": "OMEGA", "solvedOnGuess": 3},
        {"board": 2, "answer": "BIRCH", "solvedOnGuess": 4},
        {"board": 3, "answer": "SMOCK", "solvedOnGuess": 5},
        {"board": 4, "answer": "EERIE", "solvedOnGuess": 6},
    ],
}

GAME_HEURISTIC_WIN_2 = {
    "seq": 5,
    "date": "2026-08-01",
    "mode": "practice",
    "player": "heuristic",
    "won": True,
    "totalGuessesUsed": 7,
    "maxGuesses": 9,
    "boardsSolved": 4,
    "words": [
        {"board": 1, "answer": "OMEGA", "solvedOnGuess": 2},
        {"board": 2, "answer": "BIRCH", "solvedOnGuess": 4},
        {"board": 3, "answer": "SMOCK", "solvedOnGuess": 6},
        {"board": 4, "answer": "EERIE", "solvedOnGuess": 7},
    ],
}

# Two configs identical except for the logged opener count -- must land in
# separate rows once compare() groups by openers too.
GAME_CLAUDE_OPENERS_0 = {
    "seq": 7,
    "date": "2026-08-02",
    "mode": "browser",
    "player": "claude",
    "model": "claude-sonnet-5",
    "assist": "none",
    "openers": 0,
    "won": True,
    "totalGuessesUsed": 8,
    "maxGuesses": 9,
    "boardsSolved": 4,
    "words": [
        {"board": 1, "answer": "OMEGA", "solvedOnGuess": 4},
        {"board": 2, "answer": "BIRCH", "solvedOnGuess": 5},
        {"board": 3, "answer": "SMOCK", "solvedOnGuess": 7},
        {"board": 4, "answer": "EERIE", "solvedOnGuess": 8},
    ],
}

GAME_CLAUDE_OPENERS_2 = {
    **GAME_CLAUDE_OPENERS_0,
    "seq": 8,
    "openers": 2,
}

# A group with every game endedEarly, so it should be omitted from compare()
# but still counted in skipped.
GAME_ALL_EARLY = {
    "seq": 6,
    "date": "2026-08-01",
    "mode": "browser",
    "player": "claude",
    "model": "claude-opus",
    "assist": "hint",
    "won": False,
    "totalGuessesUsed": 1,
    "maxGuesses": 9,
    "boardsSolved": 0,
    "words": [
        {"board": 1, "answer": "", "solvedOnGuess": 0},
        {"board": 2, "answer": "", "solvedOnGuess": 0},
        {"board": 3, "answer": "", "solvedOnGuess": 0},
        {"board": 4, "answer": "", "solvedOnGuess": 0},
    ],
    "endedEarly": True,
}


# ---- board_positions ---------------------------------------------------------


def test_board_positions_returns_solved_on_guess_in_board_order():
    assert board_positions(GAME_CLAUDE_WIN) == [4, 5, 7, 8]


def test_board_positions_maps_unsolved_board_to_penalty():
    # board 4 unsolved (0) -> maxGuesses(9) + 1 = 10
    assert board_positions(GAME_CLAUDE_LOSS) == [7, 3, 6, 10]


# ---- per-game scorers ---------------------------------------------------------


def test_avg_position():
    assert avg_position([4, 5, 7, 8]) == pytest.approx(6.0)


def test_max_position():
    assert max_position([4, 5, 7, 8]) == 8


def test_first_position():
    assert first_position([4, 5, 7, 8]) == 4


def test_solved_in_nine_true_when_all_within_max_guesses():
    assert solved_in_nine([4, 5, 7, 8], 9) is True


def test_solved_in_nine_false_when_any_hits_penalty():
    # position 10 = maxGuesses(9) + 1 penalty, i.e. an unsolved board
    assert solved_in_nine([7, 3, 6, 10], 9) is False


def test_convex_cost_sum_of_squares():
    assert convex_cost([4, 5, 7, 8]) == 4**2 + 5**2 + 7**2 + 8**2


def test_convex_cost_penalizes_trailing_spread_boards_per_adr_example():
    # ADR-0015 example: [4,5,7,8] should score worse (higher) than [4,5,6,8]
    worse = convex_cost([4, 5, 7, 8])
    better = convex_cost([4, 5, 6, 8])
    assert worse == 154
    assert better == 141
    assert worse > better


# ---- compare -------------------------------------------------------------


def test_compare_groups_by_player_model_assist_with_correct_labels():
    panels = compare([GAME_CLAUDE_WIN, GAME_HEURISTIC_WIN])
    labels = {p.label for p in panels}
    assert labels == {"claude/claude-sonnet-5/none", "heuristic"}


def test_compare_returns_stable_sorted_order():
    panels = compare([GAME_HEURISTIC_WIN, GAME_CLAUDE_WIN])
    assert [p.label for p in panels] == sorted(p.label for p in panels)


def test_compare_excludes_ended_early_and_counts_skipped():
    panels = compare([GAME_CLAUDE_WIN, GAME_CLAUDE_LOSS, GAME_CLAUDE_ENDED_EARLY])
    assert len(panels) == 1
    panel = panels[0]
    assert panel.label == "claude/claude-sonnet-5/none"
    assert panel.games == 2
    assert panel.skipped == 1
    # one win + one loss among the two scored games -> a genuine fractional rate
    assert panel.win_rate == pytest.approx(0.5)


def test_compare_omits_config_with_zero_scored_games():
    panels = compare([GAME_ALL_EARLY, GAME_HEURISTIC_WIN])
    labels = {p.label for p in panels}
    assert "claude/claude-opus/hint" not in labels
    assert labels == {"heuristic"}


def test_compare_aggregates_win_rate_and_means():
    panels = compare([GAME_HEURISTIC_WIN, GAME_HEURISTIC_WIN_2])
    assert len(panels) == 1
    panel = panels[0]
    assert panel.games == 2
    assert panel.skipped == 0
    # both heuristic games solve all boards within maxGuesses -> win_rate 1.0
    assert panel.win_rate == pytest.approx(1.0)

    positions_1 = board_positions(GAME_HEURISTIC_WIN)  # [3,4,5,6]
    positions_2 = board_positions(GAME_HEURISTIC_WIN_2)  # [2,4,6,7]
    expected_mean_avg = (avg_position(positions_1) + avg_position(positions_2)) / 2
    expected_mean_max = (max_position(positions_1) + max_position(positions_2)) / 2
    expected_mean_first = (first_position(positions_1) + first_position(positions_2)) / 2
    expected_mean_convex = (convex_cost(positions_1) + convex_cost(positions_2)) / 2

    assert panel.mean_avg == pytest.approx(expected_mean_avg)
    assert panel.mean_max == pytest.approx(expected_mean_max)
    assert panel.mean_first == pytest.approx(expected_mean_first)
    assert panel.mean_convex == pytest.approx(expected_mean_convex)


def test_compare_returns_empty_list_for_no_games():
    assert compare([]) == []


def test_compare_splits_configs_that_differ_only_by_openers():
    panels = compare([GAME_CLAUDE_OPENERS_0, GAME_CLAUDE_OPENERS_2])
    labels = {p.label for p in panels}
    assert labels == {
        "claude/claude-sonnet-5/none · o0",
        "claude/claude-sonnet-5/none · o2",
    }
    assert len(panels) == 2
    assert all(p.games == 1 for p in panels)


def test_compare_record_without_openers_field_keeps_plain_label():
    panels = compare([GAME_CLAUDE_WIN])
    assert panels[0].label == "claude/claude-sonnet-5/none"


def test_config_panel_is_frozen_dataclass():
    panel = ConfigPanel(
        label="x",
        games=1,
        skipped=0,
        win_rate=1.0,
        mean_avg=1.0,
        mean_max=1.0,
        mean_first=1.0,
        mean_convex=1.0,
    )
    with pytest.raises(AttributeError):
        panel.label = "y"  # type: ignore[misc]


# ---- CLI -------------------------------------------------------------------


def test_main_prints_table_for_bundled_sample(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["quordle-objectives", "data/quordle_games.sample.jsonl"])
    main()
    captured = capsys.readouterr()
    assert captured.out.strip() != ""
    assert "convex" in captured.out.lower()


def test_main_prints_table_with_skipped_footer(tmp_path, monkeypatch, capsys):
    games_path = tmp_path / "games.jsonl"
    lines = "\n".join(
        __import__("json").dumps(g)
        for g in [GAME_CLAUDE_WIN, GAME_CLAUDE_LOSS, GAME_CLAUDE_ENDED_EARLY]
    )
    games_path.write_text(lines + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["quordle-objectives", str(games_path)])
    main()
    captured = capsys.readouterr()
    assert "claude/claude-sonnet-5/none" in captured.out
    assert "skipped (endedEarly): 1" in captured.out  # exact footer, right count
    assert "provisional" in captured.out.lower()


def test_main_combines_multiple_logs_into_one_table(tmp_path, monkeypatch, capsys):
    # Compare a "heuristic sweep" file and a "claude sweep" file side by side.
    import json

    heur = tmp_path / "heuristic.jsonl"
    claude = tmp_path / "claude.jsonl"
    heur.write_text(json.dumps(GAME_HEURISTIC_WIN) + "\n", encoding="utf-8")
    claude.write_text(json.dumps(GAME_CLAUDE_WIN) + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["quordle-objectives", str(heur), str(claude)])
    main()
    out = capsys.readouterr().out
    assert "heuristic" in out
    assert "claude/claude-sonnet-5/none" in out


def test_main_skips_a_missing_log_without_tracebacking(tmp_path, monkeypatch, capsys):
    # A not-yet-created log (e.g. a sweep whose first game hasn't landed) should
    # be skipped with a friendly note, not raise FileNotFoundError.
    import json

    real = tmp_path / "real.jsonl"
    real.write_text(json.dumps(GAME_HEURISTIC_WIN) + "\n", encoding="utf-8")
    missing = tmp_path / "not-there-yet.jsonl"
    monkeypatch.setattr(sys, "argv", ["quordle-objectives", str(missing), str(real)])
    main()  # must not raise
    captured = capsys.readouterr()
    assert "heuristic" in captured.out
    assert "no log yet" in captured.err


def test_main_exits_when_no_finished_games(tmp_path, monkeypatch):
    empty_path = tmp_path / "empty.jsonl"
    empty_path.write_text("", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["quordle-objectives", str(empty_path)])
    with pytest.raises(SystemExit):
        main()


def test_main_exits_when_all_games_ended_early(tmp_path, monkeypatch):
    games_path = tmp_path / "games.jsonl"
    games_path.write_text(
        __import__("json").dumps(GAME_CLAUDE_ENDED_EARLY) + "\n", encoding="utf-8"
    )
    monkeypatch.setattr(sys, "argv", ["quordle-objectives", str(games_path)])
    with pytest.raises(SystemExit):
        main()
