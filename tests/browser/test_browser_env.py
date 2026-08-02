import os

import pytest

RUN = os.getenv("RUN_BROWSER_TESTS") == "1"
pytestmark = pytest.mark.skipif(not RUN, reason="set RUN_BROWSER_TESTS=1 to drive a real browser")


def test_browser_env_plays_two_guesses():
    from quordle import wordlist
    from quordle.browser.browser_env import BrowserEnv

    allowed = wordlist.load_allowed()
    with BrowserEnv(allowed=allowed, headless=True) as env:
        assert env.num_boards == 4
        assert env.max_guesses == 9
        assert env.remaining_guesses() == 9
        result = env.submit("SLATE")
        assert result.guesses_used == 1
        assert len(result.boards) == 4
        # every board reports a 5-mark pattern (or None if already solved — unlikely on turn 1)
        for b in result.boards:
            assert b.pattern is None or len(b.pattern) == 5
        assert env.remaining_guesses() == 8
        env.submit("CURIO")
        assert env.remaining_guesses() == 7


def test_browser_env_raises_guess_rejected_for_word_the_site_refuses():
    from quordle.browser.browser_env import BrowserEnv, GuessRejected

    # "ZZZZZ" is not a real word in any Wordle-style dictionary, so the live
    # site will refuse it and the target row will never advance. It's
    # injected directly into `allowed` (bypassing quordle's own wordlist) so
    # this test exercises BrowserEnv's site-rejection handling specifically,
    # not our local allowed-guess validation (already covered by the
    # ValueError case implicitly via the `allowed` contract).
    allowed = frozenset({"ZZZZZ"})
    with BrowserEnv(allowed=allowed, headless=True) as env:
        with pytest.raises(GuessRejected):
            env.submit("ZZZZZ")
        # the rejected guess must not have consumed a turn
        assert env.remaining_guesses() == 9
