#!/usr/bin/env python3
"""
objectives.py — score and compare solver configurations from the logged games
against the full panel of ADR-0015 objectives (avg/max/first solve position,
solved-in-nine, and a provisional convex cost), tabulated side by side.

Usage:
    quordle-objectives [games.jsonl]

See docs/adr/0015-pluggable-policy-and-objective.md and
docs/superpowers/specs/2026-08-02-objective-harness-design.md for the design.
"""

import argparse
import sys
from dataclasses import dataclass

from quordle.dashboard import Game, load

# ---- per-game scorers -------------------------------------------------------


def board_positions(game: Game) -> list[int]:
    """The four boards' solvedOnGuess in board order, with an unsolved board
    (solvedOnGuess == 0) mapped to maxGuesses + 1 (a penalty position)."""
    max_guesses = game["maxGuesses"]
    return [w["solvedOnGuess"] if w["solvedOnGuess"] else max_guesses + 1 for w in game["words"]]


def avg_position(positions: list[int]) -> float:
    return sum(positions) / len(positions)


def max_position(positions: list[int]) -> int:
    return max(positions)


def first_position(positions: list[int]) -> int:
    return min(positions)


def solved_in_nine(positions: list[int], max_guesses: int) -> bool:
    """True if all four boards were solved within max_guesses (i.e. none hit
    the maxGuesses + 1 penalty position)."""
    return all(p <= max_guesses for p in positions)


def convex_cost(positions: list[int]) -> int:
    """Provisional convex weighting: sum of squares of the four positions.
    Penalizes trailing/spread boards more than a flat sum would. Constants
    are deferred per ADR-0015; retuning this is a one-line change."""
    return sum(p * p for p in positions)


# ---- comparison --------------------------------------------------------------


@dataclass(frozen=True)
class ConfigPanel:
    label: str
    games: int
    skipped: int
    win_rate: float
    mean_avg: float
    mean_max: float
    mean_first: float
    mean_convex: float


def _config_label(game: Game) -> str:
    player = game.get("player", "-")
    model = game.get("model", "-")
    assist = game.get("assist", "-")
    parts = [p for p in (player, model, assist) if p != "-"]
    label = "/".join(parts) if parts else "-"
    if "openers" in game:
        label += f" · o{game['openers']}"
    return label


_ConfigKey = tuple[str, str, str, "int | None"]


def compare(games: list[Game]) -> list[ConfigPanel]:
    """Group games by solver config (player, model, assist, openers),
    exclude endedEarly games from scoring (but count them as skipped), and
    aggregate each group's scored games into a ConfigPanel. `openers` is the
    logged fixed-opener count; games without the field (pre-feature) group
    together under None and keep their plain (suffix-free) label. Configs
    with zero scored games are omitted. Returns panels sorted by label."""
    groups: dict[_ConfigKey, list[Game]] = {}
    skipped_counts: dict[_ConfigKey, int] = {}
    labels: dict[_ConfigKey, str] = {}

    for game in games:
        key = (
            game.get("player", "-"),
            game.get("model", "-"),
            game.get("assist", "-"),
            game.get("openers"),
        )
        labels[key] = _config_label(game)
        if game.get("endedEarly"):
            skipped_counts[key] = skipped_counts.get(key, 0) + 1
            continue
        groups.setdefault(key, []).append(game)

    panels: list[ConfigPanel] = []
    for key, scored_games in groups.items():
        # scored_games is never empty here: a key only lands in `groups` via
        # the append above, which only runs for non-endedEarly games.
        positions_by_game = [board_positions(g) for g in scored_games]
        wins = sum(
            1
            for g, positions in zip(scored_games, positions_by_game, strict=True)
            if solved_in_nine(positions, g["maxGuesses"])
        )
        n = len(scored_games)
        panels.append(
            ConfigPanel(
                label=labels[key],
                games=n,
                skipped=skipped_counts.get(key, 0),
                win_rate=wins / n,
                mean_avg=sum(avg_position(p) for p in positions_by_game) / n,
                mean_max=sum(max_position(p) for p in positions_by_game) / n,
                mean_first=sum(first_position(p) for p in positions_by_game) / n,
                mean_convex=sum(convex_cost(p) for p in positions_by_game) / n,
            )
        )

    panels.sort(key=lambda p: p.label)
    return panels


# ---- CLI ----------------------------------------------------------------------


def _render_table(panels: list[ConfigPanel], total_skipped: int) -> str:
    header = f"{'config':<28}{'games':>7}{'win%':>7}{'avg':>8}{'max':>7}{'first':>7}{'convex':>9}"
    lines = [header, "-" * len(header)]
    for p in panels:
        lines.append(
            f"{p.label:<28}{p.games:>7}{100 * p.win_rate:>6.0f}%"
            f"{p.mean_avg:>8.2f}{p.mean_max:>7.2f}{p.mean_first:>7.2f}{p.mean_convex:>9.1f}"
        )
    lines.append("-" * len(header))
    lines.append(
        f"skipped (endedEarly): {total_skipped}  |  "
        "convex is a provisional sum-of-squares (ADR-0015)"
    )
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("log", nargs="?", default="data/quordle_games.jsonl")
    args = ap.parse_args()

    games = load(args.log)
    if not games:
        sys.exit("No finished games in " + args.log)

    panels = compare(games)
    if not panels:
        sys.exit("No finished games in " + args.log)

    total_skipped = sum(1 for g in games if g.get("endedEarly"))
    print(_render_table(panels, total_skipped))


if __name__ == "__main__":  # pragma: no cover — exercised by running the script, not by tests
    main()
