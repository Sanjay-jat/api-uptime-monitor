from enum import StrEnum
from typing import NamedTuple


class Status(StrEnum):
    UP = "up"
    DOWN = "down"


class Event(StrEnum):
    NONE = "none"
    WENT_DOWN = "went_down"
    RECOVERED = "recovered"


class State(NamedTuple):
    fail_count: int
    status: Status
    event: Event


def next_state(prev_fail_count: int, status: Status, ok: bool, threshold: int) -> State:
    if threshold < 1:
        raise ValueError("threshold must be >= 1")
    if ok:
        fail_count = 0
        if status == Status.DOWN:
            return State(fail_count=fail_count, status=Status.UP, event=Event.RECOVERED)
        else:
            return State(fail_count=fail_count, status=Status.UP, event=Event.NONE)
    fail_count = prev_fail_count + 1
    if status == Status.UP and fail_count >= threshold:
        return State(fail_count=fail_count, status=Status.DOWN, event=Event.WENT_DOWN)
    else:
        return State(fail_count=fail_count, status=status, event=Event.NONE)
