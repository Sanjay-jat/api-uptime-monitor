import pytest

from app.monitor import Event, State, Status, next_state


@pytest.mark.parametrize(
    ("prev", "status", "ok", "threshold", "expected"),
    [
        # fail below threshold: not DOWN yet
        (0, Status.UP, False, 3, State(1, Status.UP, Event.NONE)),
        (1, Status.UP, False, 3, State(2, Status.UP, Event.NONE)),
        # threshold pe pahuncha: DOWN, ek baar
        (2, Status.UP, False, 3, State(3, Status.DOWN, Event.WENT_DOWN)),
        (0, Status.UP, False, 1, State(1, Status.DOWN, Event.WENT_DOWN)),
        # already DOWN, another fail: no new alert
        (3, Status.DOWN, False, 3, State(4, Status.DOWN, Event.NONE)),
        # success: count reset
        (2, Status.UP, True, 3, State(0, Status.UP, Event.NONE)),
        # DOWN ke baad success: recovered
        (5, Status.DOWN, True, 3, State(0, Status.UP, Event.RECOVERED)),
    ],
    ids=[
        "first_fail_stays_up",
        "second_fail_stays_up",
        "third_fail_goes_down",
        "threshold_1_goes_down_at_once",
        "fail_while_down_no_repeat_alert",
        "success_resets_count",
        "success_while_down_recovers",
    ],
)
def test_next_state(prev, status, ok, threshold, expected):
    assert next_state(prev, status, ok, threshold) == expected


@pytest.mark.parametrize("bad", [0, -1])
def test_threshold_below_one_raises(bad):
    with pytest.raises(ValueError):
        next_state(0, Status.UP, False, bad)


def test_full_outage_one_alert_each():
    count, status = 0, Status.UP
    events = []
    for ok in [False, False, False, False, False, True]:
        count, status, event = next_state(count, status, ok, 3)
        events.append(event)
    assert events == [
        Event.NONE,
        Event.NONE,
        Event.WENT_DOWN,
        Event.NONE,
        Event.NONE,
        Event.RECOVERED,
    ]
    assert status == Status.UP
