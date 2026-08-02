# quordle-ai-experiments

Experiments in playing [Quordle](https://www.merriam-webster.com/games/quordle)
with an AI agent, logging every game, and charting how the solving goes over time.

The agent plays practice games in the browser, records each finished game as one
line of JSON, and a small Python script turns the accumulated history into a
self-contained HTML stats dashboard.

## What's here

```
quordle-ai-experiments/
├── src/quordle/                      # the installable package
│   ├── wordlist.py                   # answer/allowed word lists
│   ├── scoring.py                    # guess scoring
│   ├── board.py                      # single-board state
│   ├── engine.py                     # multi-board sim engine
│   ├── policy.py                     # heuristic guessing policies
│   ├── solver.py                     # drives a policy to a solved/failed game
│   ├── provider.py                   # Claude API access for LLM-played games
│   ├── llm_policy.py                 # policy backed by an LLM provider
│   ├── runner.py                     # plays games, appends JSONL (quordle-sim)
│   └── dashboard.py                  # reads the log → builds the dashboard + PNGs (quordle-stats)
├── data/
│   ├── quordle_games.jsonl           # the running game log (gitignored)
│   └── quordle_games.sample.jsonl    # 2 example rows, committed to show the format
├── quordle_dashboard.html            # generated output (gitignored)
└── charts/                           # generated PNGs (gitignored)
```

The game log itself is **gitignored** — the repo is about the tooling, not the
data churn (a daily run would otherwise add a commit per game). Keep your real
log at `data/quordle_games.jsonl`; the committed `*.sample.jsonl` documents the
shape.

## Usage

```bash
pip install -e ".[dev]"
quordle-sim -n 100 --seed 0                       # heuristic games -> data/quordle_games.jsonl
quordle-sim --player claude -n 5 --assist none    # Claude-played games (needs API access)
quordle-stats                                     # build quordle_dashboard.html

python -m playwright install chromium             # one-time, needed for --env browser
quordle-sim --env browser --player claude         # plays one live quordle.com game (needs ANTHROPIC_API_KEY)
```

`--env browser` plays a single live game against beta.quordle.com via Playwright
(headless by default; pass `--headed` to watch it) and logs it with `mode:"browser"`
instead of `mode:"sim"`/`mode:"claude"`.

Open `quordle_dashboard.html` in any browser.

## Data format

One JSON object per line. Each board carries `solvedOnGuess`: the guess number
(1–9) a board was solved on, or **0 if it was never solved**.

```json
{"seq": 1, "date": "2026-08-01", "mode": "practice",
 "guesses": ["SLATE", "CURIO", "NYMPH", "PILOT", "PLANK", "FRIES", "RABID", "RISER"],
 "totalGuessesUsed": 8, "maxGuesses": 9, "boardsSolved": 4, "won": true,
 "words": [
   {"board": 1, "answer": "PILOT", "solvedOnGuess": 4},
   {"board": 2, "answer": "PLANK", "solvedOnGuess": 5},
   {"board": 3, "answer": "RISER", "solvedOnGuess": 8},
   {"board": 4, "answer": "RABID", "solvedOnGuess": 7}
 ]}
```

Adding a game is just appending a line — no schema migration, no database.

## The dashboard

Six charts plus a stat row (games, win rate, boards-solved rate, avg guesses on
wins, best game):

- **Guess distribution** — total guesses to finish each game (Wordle-style), with a bar for losses.
- **When boards fall** — histogram of `solvedOnGuess` across all boards, including an "X" bucket for unsolved.
- **Boards over time** — boards solved per game, by sequence.
- **Guesses trend** — per-game guesses with a running average.
- **Solving pace** — average number of boards done by the end of each guess N.
- **Board difficulty** — average solve position per board position (1–4).

## Roadmap / experiment ideas

- Opener effectiveness once more than one opening set has been tried.
- Solver-strategy comparisons (fixed openers vs. adaptive).
- A live web view (e.g. a small Spring Boot service) instead of static HTML.
- Automated daily runs that append to the log and regenerate the dashboard.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
