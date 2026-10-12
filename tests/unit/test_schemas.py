import pytest
from pydantic import ValidationError

from app.schemas import Credentials, UserOut


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
