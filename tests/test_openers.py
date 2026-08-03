from quordle import wordlist
from quordle.openers import OPENERS, _format_report, best_openers, expected_remaining, signature
from quordle.scoring import Mark, score

# Synthetic answers: single-letter-repeated words. Small and hand-verifiable
# -- NOT the bundled 2315/12972 lists (that computation is a slow, one-off
# manual step; see openers.py's OPENERS constant and its printer).
ANSWERS = ["AAAAA", "BBBBB", "CCCCC", "DDDDD", "EEEEE", "FFFFF", "GGGGG"]


def test_signature_is_per_opener_score_tuple():
    assert signature(("ABCDE",), "AAAAA") == (score("ABCDE", "AAAAA"),)
    assert signature(("ABCDE", "FGHIJ"), "FFFFF") == (
        score("ABCDE", "FFFFF"),
        score("FGHIJ", "FFFFF"),
    )


def test_expected_remaining_perfect_split_is_one():
    # ABCDE gives each of A..E its own green position, and FFFFF/GGGGG both
    # collapse to all-grey -- but that's still a *different* pattern from any
    # of A..E's, so every answer above lands in its own singleton bucket
    # only once we also check F vs G don't collide. They DO collide (both
    # all-grey), so this single opener is NOT yet a perfect split -- see the
    # next test for the exact value.
    er = expected_remaining(("ABCDE",), ANSWERS)
    assert er == (5 * 1 + 2 * 2) / 7  # A,B,C,D,E singleton; F,G share a bucket


def test_second_opener_lowers_expected_remaining_to_the_perfect_split():
    # FGHIJ distinguishes F from G (green at pos0 / pos1 respectively) without
    # disturbing A..E's already-unique buckets -- driving expected_remaining
    # down to the theoretical minimum of 1.0 (every answer in its own bucket).
    first_only = expected_remaining(("ABCDE",), ANSWERS)
    with_second = expected_remaining(("ABCDE", "FGHIJ"), ANSWERS)
    assert with_second < first_only
    assert with_second == 1.0


def test_best_openers_picks_the_hand_verified_best_single_opener():
    pool = ["ABCDE", "FGHIJ", "KLMNO", "AAAAA"]
    assert best_openers(ANSWERS, pool, 1) == ["ABCDE"]


def test_best_openers_greedy_second_pick_is_the_true_complement():
    # KLMNO and AAAAA are decoys that don't touch F/G's shared bucket at all;
    # FGHIJ is the only pool word that actually helps -- greedy must find it.
    pool = ["ABCDE", "FGHIJ", "KLMNO", "AAAAA"]
    assert best_openers(ANSWERS, pool, 2) == ["ABCDE", "FGHIJ"]


def test_best_openers_never_repeats_a_word():
    pool = ["ABCDE", "FGHIJ"]
    chosen = best_openers(ANSWERS, pool, 2)
    assert len(chosen) == len(set(chosen)) == 2


def test_signature_pattern_values_are_marks():
    pattern = signature(("ABCDE",), "AAAAA")[0]
    assert all(isinstance(mark, Mark) for mark in pattern)


def test_format_report_shows_cumulative_expected_remaining_per_opener():
    report = _format_report(["ABCDE", "FGHIJ"], ANSWERS)
    lines = report.splitlines()
    assert len(lines) == 2
    assert lines[0].startswith("1: ABCDE")
    assert lines[1].startswith("2: ABCDE FGHIJ")
    assert "expected_remaining=1.0000" in lines[1]  # perfect split, hand-verified above


def test_openers_constant_is_three_five_letter_uppercase_words():
    assert len(OPENERS) == 3
    assert all(len(w) == 5 and w.isupper() and w.isalpha() for w in OPENERS)
    assert len(set(OPENERS)) == 3  # no repeats


def test_openers_constant_words_are_in_the_bundled_allowed_list():
    allowed = wordlist.load_allowed()
    assert all(w in allowed for w in OPENERS)
