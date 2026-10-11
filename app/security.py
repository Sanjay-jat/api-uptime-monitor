import bcrypt


def hash_password(plain: str) -> str:
    hashed = bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()
    return hashed


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode(), hashed.encode())
