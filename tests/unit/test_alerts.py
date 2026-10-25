import hashlib
import hmac
import json
from datetime import UTC, datetime

from app.alerts import build_body, sign
from app.monitor import Event

NOW = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)


def test_build_body_fields():
    body = build_body(Event.WENT_DOWN, 7, "https://a.example.com", NOW)
    assert json.loads(body) == {
        "event": "went_down",
        "endpoint_id": 7,
        "url": "https://a.example.com",
        "at": "2026-01-01T12:00:00+00:00",
    }


def test_build_body_recovered_event():
    body = build_body(Event.RECOVERED, 7, "https://a.example.com", NOW)
    assert json.loads(body)["event"] == "recovered"


def test_build_body_same_input_same_bytes():
    a = build_body(Event.WENT_DOWN, 1, "https://x.com", NOW)
    b = build_body(Event.WENT_DOWN, 1, "https://x.com", NOW)
    assert a == b
    assert b" " not in a  # compact


def test_sign_matches_stdlib_hmac():
    expected = hmac.new(b"s3cret", b"hello", hashlib.sha256).hexdigest()
    assert sign("s3cret", b"hello") == expected
    assert len(expected) == 64


def test_sign_changes_with_secret():
    assert sign("a", b"body") != sign("b", b"body")


def test_sign_changes_with_body():
    assert sign("a", b"body1") != sign("a", b"body2")
