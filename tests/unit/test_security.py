from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.security import (
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


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
    sig = ("B" if parts[2][0] == "A" else "A") + parts[2][1:]
    tampered_token = f"{parts[0]}.{parts[1]}.{sig}"
    with pytest.raises(jwt.InvalidTokenError):
        decode_access_token(tampered_token)


def test_wrong_secret_token():
    token = jwt.encode(
        {"sub": "1", "exp": datetime.now(timezone.utc) + timedelta(seconds=60)},
        "wrong-secret-" + "x" * 32,
        algorithm="HS256",
    )
    with pytest.raises(jwt.InvalidSignatureError):
        decode_access_token(token)


def test_refresh_token_is_random_and_long():
    a = generate_refresh_token()
    b = generate_refresh_token()

    assert a != b
    assert len(a) >= 43


def test_refresh_hash_is_deterministic():
    t = generate_refresh_token()

    assert hash_refresh_token(t) == hash_refresh_token(t)


def test_refresh_hash_shape():
    h = hash_refresh_token("abc")

    assert len(h) == 64
    assert h != "abc"


def test_refresh_hash_known_value():
    assert (
        hash_refresh_token("abc")
        == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad"
    )
