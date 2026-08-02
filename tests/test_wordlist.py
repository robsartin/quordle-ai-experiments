from quordle import wordlist


def test_answers_are_five_letter_upper():
    answers = wordlist.load_answers()
    assert len(answers) > 2000
    assert all(len(w) == 5 and w.isupper() and w.isalpha() for w in answers)
    assert "CRANE" in answers


def test_allowed_superset_of_answers():
    answers = set(wordlist.load_answers())
    allowed = wordlist.load_allowed()
    assert answers <= allowed
    assert "SLATE" in allowed and "CURIO" in allowed
    assert all(len(w) == 5 for w in allowed)
