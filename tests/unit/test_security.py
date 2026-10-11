from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.security import create_access_token, decode_access_token, hash_password, verify_password


def test_hash_is_not_plaintext():
    password = "mysecret"
    hashed = hash_password(password)
    assert hashed != password


def test_verify_correct_password():
    password = "mysecret"
    hashed = hash_password(password)
    assert verify_password(password, hashed) is True


def test_verify_wrong_password():
    password = "mysecret"
    wrong_password = "wrongpassword"
    hashed = hash_password(password)
    assert verify_password(wrong_password, hashed) is False


def test_hash_is_salted():
    password = "mysecret"
    hashed1 = hash_password(password)
    hashed2 = hash_password(password)
    assert hashed1 != hashed2


def test_token_roundtrip():
    assert decode_access_token(create_access_token(42))["sub"] == "42"


def test_expired_token():
    token = create_access_token(1, expires_delta=timedelta(seconds=-1))
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(token)


def test_tampered_token():
    token = create_access_token(42)
    parts = token.split(".")
    tampered_payload = parts[1][::-1]  # Reverse the payload part
    tampered_token = f"{parts[0]}.{tampered_payload}.{parts[2]}"
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(tampered_token)


def test_wrong_secret_token():
    token = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(seconds=60)},
        "wrong-secret-" + "x" * 32,
        algorithm="HS256",
    )
    pytest.raises(jwt.InvalidSignatureError, decode_access_token, token)
