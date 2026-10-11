"""Top-up sweep (issue #39): keep playing until N games have *completed*."""


def test_backoff_delay_doubles_per_consecutive_throttle_up_to_the_cap():
    from quordle.sweep import backoff_delay

    delays = [backoff_delay(n, base=5.0, cap=60.0) for n in (1, 2, 3, 4, 5, 6)]
    assert delays == [5.0, 10.0, 20.0, 40.0, 60.0, 60.0]


def test_backoff_delay_is_zero_when_nothing_has_been_throttled():
    from quordle.sweep import backoff_delay

    assert backoff_delay(0, base=5.0, cap=60.0) == 0.0
