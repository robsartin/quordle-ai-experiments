from quordle.dashboard import summary


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
