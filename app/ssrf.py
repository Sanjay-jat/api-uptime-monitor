import asyncio
import ipaddress
import socket
from urllib.parse import urlsplit


class UnsafeURLError(ValueError):
    pass


def _get_host(url: str) -> str:
    try:
        p = urlsplit(url)
        _ = p.port
    except ValueError:
        raise UnsafeURLError("invalid URL") from None

    if p.scheme not in {"http", "https"}:
        raise UnsafeURLError("scheme must be http or https")
    if p.username is not None or p.password is not None:
        raise UnsafeURLError("userinfo not allowed")
    if not p.hostname:
        raise UnsafeURLError("missing host")
    return p.hostname


def _is_blocked(ip) -> bool:
    mapped = getattr(ip, "ipv4_mapped", None)
    if mapped is not None:
        ip = mapped
    return not ip.is_global or ip.is_multicast


async def validate_public_url(url: str) -> None:
    host = _get_host(url)
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError):
        raise UnsafeURLError("cannot resolve host") from None
    for info in infos:
        addr = info[4][0]
        if _is_blocked(ipaddress.ip_address(addr)):
            raise UnsafeURLError("host resolves to blocked IP")
