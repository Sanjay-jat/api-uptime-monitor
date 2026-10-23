import pytest
from pydantic import ValidationError

from app.schemas import Credentials, EndpointCreate, EndpointUpdate, UserOut


def test_email_lowercased():
    c = Credentials.model_validate({"email": "TEST@EXAMPLE.COM", "password": "password1"})
    assert c.email == "test@example.com"


def test_invalid_email():
    with pytest.raises(ValidationError):
        Credentials.model_validate({"email": "invalid-email", "password": "password1"})


def test_password_too_short():
    with pytest.raises(ValidationError):
        Credentials.model_validate({"email": "test@example.com", "password": "a" * 7})


def test_password_too_long_ascii():
    with pytest.raises(ValidationError):
        Credentials.model_validate({"email": "test@example.com", "password": "a" * 73})


def test_password_too_long_bytes():
    with pytest.raises(ValidationError):
        Credentials.model_validate({"email": "test@example.com", "password": "é" * 40})


def test_user_out_hides_hash():
    assert "password_hash" not in UserOut.model_fields


def test_password_min_length_ok():
    c = Credentials.model_validate({"email": "test@example.com", "password": "a" * 8})
    assert c.password == "a" * 8


def test_password_max_bytes_ok():
    c = Credentials.model_validate({"email": "test@example.com", "password": "a" * 72})
    assert c.password == "a" * 72


def valid(**over):
    data = {"url": "https://example.com", "interval_seconds": 300}
    data.update(over)
    return data


def test_create_valid_uses_defaults():
    e = EndpointCreate(**valid())
    assert e.method == "GET"
    assert e.timeout_seconds == 10
    assert e.expected_status == 200


@pytest.mark.parametrize("n", [60, 86400])
def test_create_interval_boundaries_accepted(n):
    EndpointCreate(**valid(interval_seconds=n))


@pytest.mark.parametrize(
    "over",
    [
        {"url": "ftp://example.com"},
        {"url": "http://user:pass@example.com"},
        {"url": "not a url"},
        {"url": "http://" + "a" * 2050},
        {"interval_seconds": 59},
        {"interval_seconds": 86401},
        {"timeout_seconds": 0},
        {"timeout_seconds": 31},
        {"expected_status": 99},
        {"expected_status": 600},
        {"method": "POST"},
        {"user_id": 5},
    ],
)
def test_create_invalid_rejected(over):
    with pytest.raises(ValidationError):
        EndpointCreate(**valid(**over))


def test_update_empty_is_allowed_and_changes_nothing():
    assert EndpointUpdate().model_dump(exclude_none=True) == {}


def test_update_partial_only_sets_given_fields():
    u = EndpointUpdate(is_active=False)
    assert u.model_dump(exclude_none=True) == {"is_active": False}


def test_update_bad_url_rejected():
    with pytest.raises(ValidationError):
        EndpointUpdate(url="ftp://example.com")


def test_update_extra_field_rejected():
    with pytest.raises(ValidationError):
        EndpointUpdate(user_id=5)
