import pytest

from app import cache


@pytest.fixture(autouse=True)
def _clean_cache():
    cache.clear()
    yield
    cache.clear()


def _p(endpoint_id, status="up"):
    return {"endpoint_id": endpoint_id, "status": status}


def test_unknown_user_gives_empty_list():
    assert cache.get_user_statuses(1) == []


def test_set_then_get():
    cache.set_status(1, 10, _p(10))
    assert cache.get_user_statuses(1) == [_p(10)]


def test_set_same_endpoint_replaces():
    cache.set_status(1, 10, _p(10, "up"))
    cache.set_status(1, 10, _p(10, "down"))
    assert cache.get_user_statuses(1) == [_p(10, "down")]


def test_users_are_isolated():
    cache.set_status(1, 10, _p(10))
    cache.set_status(2, 20, _p(20))
    assert cache.get_user_statuses(1) == [_p(10)]
    assert cache.get_user_statuses(2) == [_p(20)]


def test_remove_one_keeps_other():
    cache.set_status(1, 10, _p(10))
    cache.set_status(1, 11, _p(11))
    cache.remove(1, 10)
    assert cache.get_user_statuses(1) == [_p(11)]


def test_remove_last_endpoint_drops_user_entry():
    cache.set_status(1, 10, _p(10))
    cache.remove(1, 10)
    assert cache.get_user_statuses(1) == []
    assert 1 not in cache._store


@pytest.mark.parametrize(("user_id", "endpoint_id"), [(99, 1), (1, 99)])
def test_remove_missing_is_noop(user_id, endpoint_id):
    cache.set_status(1, 10, _p(10))
    cache.remove(user_id, endpoint_id)
    assert cache.get_user_statuses(1) == [_p(10)]


def test_returned_list_is_a_copy():
    cache.set_status(1, 10, _p(10))
    cache.get_user_statuses(1).clear()
    assert cache.get_user_statuses(1) == [_p(10)]


def test_clear_empties_everything():
    cache.set_status(1, 10, _p(10))
    cache.set_status(2, 20, _p(20))
    cache.clear()
    assert cache.get_user_statuses(1) == []
    assert cache.get_user_statuses(2) == []
