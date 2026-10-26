import pytest

from app.routers.history import uptime_percent


@pytest.mark.parametrize(
    ("ok", "total", "expected"),
    [(0, 0, None), (0, 5, 0.0), (5, 5, 100.0), (1, 3, 33.33), (2, 3, 66.67)],
)
def test_uptime_percent(ok, total, expected):
    assert uptime_percent(ok, total) == expected
