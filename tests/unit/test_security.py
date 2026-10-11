from app.security import hash_password, verify_password


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
