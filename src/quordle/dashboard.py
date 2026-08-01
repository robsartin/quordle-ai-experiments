#!/usr/bin/env python3
"""
dashboard.py — read a Quordle game history (JSONL) and build a self-contained
HTML dashboard (charts embedded as base64 PNGs).

Usage:
    quordle-stats [games.jsonl] [-o dashboard.html] [--png-dir charts/]

Input format: one JSON object per line, e.g.
    {"seq":1,"date":"2026-08-01","mode":"practice",
     "guesses":["SLATE","CURIO",...],"totalGuessesUsed":7,"maxGuesses":9,
     "boardsSolved":4,"won":true,
     "words":[{"board":1,"answer":"CRESS","solvedOnGuess":7}, ...]}

Key field: words[].solvedOnGuess  ->  1..maxGuesses if solved, 0 if unsolved.
"""

import argparse
import base64
import io
import json
import os
import sys
from collections import Counter, defaultdict
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.ticker import MaxNLocator

Game = dict[str, Any]

# ---- palette (cohesive, light theme) -------------------------------------
INK = "#0f172a"
MUTED = "#64748b"
GRID = "#e2e8f0"
PRIMARY = "#6366f1"  # indigo
GREEN = "#22c55e"
AMBER = "#eab308"
RED = "#ef4444"
BOARD_COLORS = ["#6366f1", "#06b6d4", "#f59e0b", "#ec4899"]  # boards 1-4

plt.rcParams.update(
    {
        "figure.facecolor": "white",
        "axes.facecolor": "white",
        "axes.edgecolor": GRID,
        "axes.labelcolor": INK,
        "text.color": INK,
        "xtick.color": MUTED,
        "ytick.color": MUTED,
        "font.size": 11,
        "axes.grid": True,
        "grid.color": GRID,
        "grid.linewidth": 1,
        "axes.axisbelow": True,
        "axes.spines.top": False,
        "axes.spines.right": False,
    }
)


def load(path: str) -> list[Game]:
    games: list[Game] = []
    with open(path) as fh:
        for line in fh:
            line = line.strip()
            if line:
                games.append(json.loads(line))
    games.sort(key=lambda g: g.get("seq", 0))
    return games


def fig_to_b64(fig: Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=130, bbox_inches="tight")
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode("ascii")


def save_png(fig_b64: str, path: str) -> None:
    with open(path, "wb") as fh:
        fh.write(base64.b64decode(fig_b64))


# ---- charts ---------------------------------------------------------------
def chart_guess_distribution(games: list[Game]) -> str:
    maxg = max(g["maxGuesses"] for g in games)
    counts = Counter(g["totalGuessesUsed"] for g in games if g["won"])
    losses = sum(1 for g in games if not g["won"])
    xs = list(range(min(counts) if counts else 4, maxg + 1))
    ys = [counts.get(x, 0) for x in xs]
    labels = [str(x) for x in xs]
    if losses:
        xs.append(maxg + 1)
        ys.append(losses)
        labels.append("X")
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    bars = ax.bar(
        range(len(xs)),
        ys,
        color=[RED if lbl == "X" else PRIMARY for lbl in labels],
        width=0.66,
    )
    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels(labels)
    ax.set_xlabel("Total guesses to finish the game  (X = not solved)")
    ax.set_ylabel("Games")
    ax.set_title("Guess distribution", fontweight="bold", loc="left")
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    for b, y in zip(bars, ys, strict=True):
        if y:
            ax.text(
                b.get_x() + b.get_width() / 2,
                y + 0.05,
                str(y),
                ha="center",
                va="bottom",
                fontsize=10,
                color=INK,
            )
    return fig_to_b64(fig)


def chart_solve_position(games: list[Game]) -> str:
    maxg = max(g["maxGuesses"] for g in games)
    solved: Counter[int] = Counter()
    unsolved = 0
    for g in games:
        for w in g["words"]:
            s = w["solvedOnGuess"]
            if s and s > 0:
                solved[s] += 1
            else:
                unsolved += 1
    xs = list(range(1, maxg + 1))
    ys = [solved.get(x, 0) for x in xs]
    labels = [str(x) for x in xs]
    if unsolved:
        xs.append(maxg + 1)
        ys.append(unsolved)
        labels.append("X")
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    bars = ax.bar(
        range(len(xs)),
        ys,
        color=[RED if lbl == "X" else GREEN for lbl in labels],
        width=0.66,
    )
    ax.set_xticks(range(len(xs)))
    ax.set_xticklabels(labels)
    ax.set_xlabel("Guess number a board was solved on  (X = never)")
    ax.set_ylabel("Boards")
    ax.set_title("When individual boards fall", fontweight="bold", loc="left")
    ax.yaxis.set_major_locator(MaxNLocator(integer=True))
    for b, y in zip(bars, ys, strict=True):
        if y:
            ax.text(
                b.get_x() + b.get_width() / 2,
                y + 0.05,
                str(y),
                ha="center",
                va="bottom",
                fontsize=10,
                color=INK,
            )
    return fig_to_b64(fig)


def chart_boards_over_time(games: list[Game]) -> str:
    seqs = [g.get("seq", i + 1) for i, g in enumerate(games)]
    boards = [g["boardsSolved"] for g in games]
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    ax.plot(seqs, boards, "-o", color=PRIMARY, lw=2, ms=6)
    ax.axhline(4, color=GREEN, ls="--", lw=1, alpha=0.7)
    ax.text(seqs[-1], 4.02, "perfect (4/4)", color=GREEN, ha="right", va="bottom", fontsize=9)
    ax.set_ylim(0, 4.4)
    ax.set_yticks([0, 1, 2, 3, 4])
    ax.set_xlabel("Game #")
    ax.set_ylabel("Boards solved")
    ax.set_title("Boards solved per game", fontweight="bold", loc="left")
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    return fig_to_b64(fig)


def chart_avg_guess_trend(games: list[Game]) -> str:
    seqs = [g.get("seq", i + 1) for i, g in enumerate(games)]
    # count a loss as maxGuesses+1 (penalty) so the line reflects failures
    vals = [g["totalGuessesUsed"] if g["won"] else g["maxGuesses"] + 1 for g in games]
    # cumulative average
    cum = []
    run = 0
    for i, v in enumerate(vals):
        run += v
        cum.append(run / (i + 1))
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    ax.plot(seqs, vals, "-o", color="#cbd5e1", lw=1.5, ms=5, label="game")
    ax.plot(seqs, cum, "-", color=AMBER, lw=2.5, label="running average")
    ax.set_xlabel("Game #")
    ax.set_ylabel("Guesses used")
    ax.set_title("Guesses per game & running average", fontweight="bold", loc="left")
    ax.xaxis.set_major_locator(MaxNLocator(integer=True))
    ax.legend(frameon=False, fontsize=9, loc="upper right")
    return fig_to_b64(fig)


def chart_cumulative_solves(games: list[Game]) -> str:
    """Average number of boards solved by the end of guess N (pacing curve)."""
    maxg = max(g["maxGuesses"] for g in games)
    xs = list(range(1, maxg + 1))
    avg = []
    for n in xs:
        total = 0
        for g in games:
            total += sum(
                1 for w in g["words"] if w["solvedOnGuess"] and 0 < w["solvedOnGuess"] <= n
            )
        avg.append(total / len(games))
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    ax.plot(xs, avg, "-o", color=PRIMARY, lw=2.5, ms=6)
    ax.fill_between(xs, avg, color=PRIMARY, alpha=0.10)
    ax.set_ylim(0, 4.2)
    ax.set_yticks([0, 1, 2, 3, 4])
    ax.set_xlabel("By end of guess #")
    ax.set_ylabel("Avg boards solved")
    ax.set_title("Solving pace (avg boards done by guess N)", fontweight="bold", loc="left")
    return fig_to_b64(fig)


def chart_board_difficulty(games: list[Game]) -> str:
    """Average solve guess per board position (blanks counted as maxGuesses+1)."""
    maxg = max(g["maxGuesses"] for g in games)
    by_pos: dict[int, list[int]] = defaultdict(list)
    for g in games:
        for w in g["words"]:
            s = w["solvedOnGuess"]
            by_pos[w["board"]].append(s if s and s > 0 else maxg + 1)
    positions = sorted(by_pos)
    means = [sum(by_pos[p]) / len(by_pos[p]) for p in positions]
    fig, ax = plt.subplots(figsize=(6.6, 3.4))
    bars = ax.bar(
        [f"Board {p}" for p in positions],
        means,
        color=[BOARD_COLORS[(p - 1) % 4] for p in positions],
        width=0.6,
    )
    ax.set_ylabel("Avg guess solved on")
    ax.set_title("Difficulty by board position", fontweight="bold", loc="left")
    for b, m in zip(bars, means, strict=True):
        ax.text(
            b.get_x() + b.get_width() / 2,
            m + 0.05,
            f"{m:.1f}",
            ha="center",
            va="bottom",
            fontsize=10,
            color=INK,
        )
    return fig_to_b64(fig)


# ---- summary stats --------------------------------------------------------
def summary(games: list[Game]) -> dict[str, Any]:
    n = len(games)
    wins = sum(1 for g in games if g["won"])
    total_boards = sum(len(g["words"]) for g in games)
    boards_solved = sum(g["boardsSolved"] for g in games)
    won_games = [g for g in games if g["won"]]
    avg_guesses = sum(g["totalGuessesUsed"] for g in won_games) / len(won_games) if won_games else 0
    best = min((g["totalGuessesUsed"] for g in won_games), default=0)
    return {
        "games": n,
        "win_rate": f"{100 * wins / n:.0f}%" if n else "0%",
        "board_rate": f"{100 * boards_solved / total_boards:.0f}%" if total_boards else "0%",
        "avg_guesses": f"{avg_guesses:.1f}" if won_games else "—",
        "best": best or "—",
    }


# ---- html -----------------------------------------------------------------
def build_html(games: list[Game], charts: dict[str, str], stats: dict[str, Any]) -> str:
    def card(title: str, b64: str) -> str:
        return f'<div class="card"><img alt="{title}" src="data:image/png;base64,{b64}"></div>'

    stat_tiles = "".join(
        f'<div class="tile"><div class="v">{v}</div><div class="k">{k}</div></div>'
        for k, v in [
            ("games", stats["games"]),
            ("win rate", stats["win_rate"]),
            ("boards solved", stats["board_rate"]),
            ("avg guesses (wins)", stats["avg_guesses"]),
            ("best game", stats["best"]),
        ]
    )
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Quordle Stats Dashboard</title>
<style>
  body{{margin:0;background:#f8fafc;color:{INK};padding:28px 18px;
       font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Arial,sans-serif}}
  .wrap{{max-width:1040px;margin:0 auto}}
  h1{{font-size:1.5rem;margin:0 0 2px}}
  .sub{{color:{MUTED};margin:0 0 22px;font-size:.92rem}}
  .tiles{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-bottom:22px}}
  .tile{{background:#fff;border:1px solid {GRID};border-radius:12px;padding:14px 12px;text-align:center}}
  .tile .v{{font-size:1.6rem;font-weight:800;color:{PRIMARY}}}
  .tile .k{{font-size:.72rem;color:{MUTED};text-transform:uppercase;letter-spacing:.04em;margin-top:2px}}
  .grid{{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}}
  .card{{background:#fff;border:1px solid {GRID};border-radius:12px;padding:10px}}
  .card img{{width:100%;height:auto;display:block}}
  @media(max-width:760px){{.grid{{grid-template-columns:1fr}}.tiles{{grid-template-columns:repeat(2,1fr)}}}}
</style></head><body><div class="wrap">
<h1>🟩 Quordle Stats</h1>
<p class="sub">{stats["games"]} games · generated from quordle_games.jsonl</p>
<div class="tiles">{stat_tiles}</div>
<div class="grid">
{card("Guess distribution", charts["guess_dist"])}
{card("When boards fall", charts["solve_pos"])}
{card("Boards over time", charts["boards_time"])}
{card("Guesses trend", charts["avg_trend"])}
{card("Solving pace", charts["cum_solves"])}
{card("Board difficulty", charts["board_diff"])}
</div></div></body></html>"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("games", nargs="?", default="data/quordle_games.jsonl")
    ap.add_argument("-o", "--out", default="quordle_dashboard.html")
    ap.add_argument(
        "--png-dir", default=None, help="also write individual chart PNGs to this directory"
    )
    args = ap.parse_args()

    games = load(args.games)
    if not games:
        sys.exit("No games found in " + args.games)

    charts = {
        "guess_dist": chart_guess_distribution(games),
        "solve_pos": chart_solve_position(games),
        "boards_time": chart_boards_over_time(games),
        "avg_trend": chart_avg_guess_trend(games),
        "cum_solves": chart_cumulative_solves(games),
        "board_diff": chart_board_difficulty(games),
    }
    stats = summary(games)
    html = build_html(games, charts, stats)
    with open(args.out, "w") as fh:
        fh.write(html)
    print(f"Wrote {args.out}  ({stats['games']} games, win rate {stats['win_rate']})")

    if args.png_dir:
        os.makedirs(args.png_dir, exist_ok=True)
        for name, b64 in charts.items():
            save_png(b64, os.path.join(args.png_dir, name + ".png"))
        print("Wrote PNGs to", args.png_dir)


if __name__ == "__main__":
    main()
