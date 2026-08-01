from quordle.scoring import Mark, score

G, Y, X = Mark.GREEN, Mark.YELLOW, Mark.GREY


def test_all_green_when_equal():
    assert score("CRANE", "CRANE") == (G, G, G, G, G)


def test_greens_and_yellows():
    assert score("ARISE", "RAISE") == (Y, Y, G, G, G)


def test_duplicate_letter_in_guess_single_in_answer():
    result = score("SASSY", "BASIS")
    assert result[0] == Mark.YELLOW
    assert result[2] == Mark.GREEN
    assert result[3] == Mark.GREY


def test_case_insensitive():
    assert score("crane", "crane") == (G, G, G, G, G)
