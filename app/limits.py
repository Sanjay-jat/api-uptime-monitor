from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)


def user_key(request: Request) -> str:
    uid = getattr(request.state, "user_id", None)
    return f"user:{uid}" if uid is not None else get_remote_address(request)
