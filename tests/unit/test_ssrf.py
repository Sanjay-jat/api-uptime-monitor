import asyncio
import ipaddress
import socket

import pytest
from hypothesis import given
from hypothesis import strategies as st

from app import ssrf
from app.ssrf import UnsafeURLError, _get_host, _is_blocked, validate_public_url

BAD_URLS = [
    "ftp://example.com",
    "file:///etc/passwd",
    "example.com",
    "",
    "http://user:pass@example.com",
    "http://@example.com",
    "http://",
    "http://:80",
    "http://a:99999",
    "http://[::1",
]


@pytest.mark.parametrize("url", BAD_URLS)
def test_bad_url_rejected(url):
    with pytest.raises(UnsafeURLError):
        _get_host(url)


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://Example.com:8080/a?x=1", "example.com"),
        ("http://example.com", "example.com"),
        ("http://[::1]/", "::1"),
        ("http://127.0.0.1", "127.0.0.1"),
    ],
)
def test_good_url_returns_lowercase_host(url, expected):
    assert _get_host(url) == expected


def test_error_message_does_not_echo_url():
    with pytest.raises(UnsafeURLError) as exc_info:
        _get_host("ftp://secret-host")
    assert "secret-host" not in str(exc_info.value)


BLOCKED_IPS = [
    "127.0.0.1",
    "10.0.0.1",
    "172.16.0.1",
    "172.31.255.255",
    "192.168.1.1",
    "169.254.169.254",
    "0.0.0.0",
    "100.64.0.1",
    "224.0.0.1",
    "::1",
    "::",
    "fc00::1",
    "fd12::1",
    "fe80::1",
    "ff02::1",
    "::ffff:127.0.0.1",
    "::ffff:10.0.0.1",
]

PUBLIC_IPS = [
    "8.8.8.8",
    "1.1.1.1",
    "93.184.216.34",
    "172.15.255.255",
    "172.32.0.0",
    "2606:4700:4700::1111",
]


@pytest.mark.parametrize("addr", BLOCKED_IPS)
def test_blocked_ip(addr):
    assert _is_blocked(ipaddress.ip_address(addr)) is True


@pytest.mark.parametrize("addr", PUBLIC_IPS)
def test_public_ip_allowed(addr):
    assert _is_blocked(ipaddress.ip_address(addr)) is False


BLOCKED_URLS = [
    "http://localhost",
    "http://127.0.0.1",
    "http://127.1",
    "http://0",
    "http://10.0.0.1",
    "http://172.16.0.1",
    "http://192.168.1.1",
    "http://169.254.169.254",
    "http://0x7f000001",
    "http://2130706433",
    "http://017700000001",
    "http://[::1]",
    "http://[fc00::1]",
    "http://[fe80::1]",
    "http://[::ffff:127.0.0.1]",
]


@pytest.mark.parametrize("url", BLOCKED_URLS)
def test_blocked_url_rejected(url):
    with pytest.raises(UnsafeURLError):
        asyncio.run(validate_public_url(url))


def fake_dns(monkeypatch, *addrs):
    def fake(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (a, 0)) for a in addrs]

    monkeypatch.setattr(socket, "getaddrinfo", fake)


def test_hostname_resolving_to_private_ip_rejected(monkeypatch):
    fake_dns(monkeypatch, "10.0.0.5")
    with pytest.raises(UnsafeURLError):
        asyncio.run(validate_public_url("http://innocent.example.com"))


def test_one_private_ip_among_public_rejected(monkeypatch):
    fake_dns(monkeypatch, "93.184.216.34", "192.168.1.1")
    with pytest.raises(UnsafeURLError):
        asyncio.run(validate_public_url("http://mixed.example.com"))


def test_public_hostname_accepted(monkeypatch):
    fake_dns(monkeypatch, "93.184.216.34")
    asyncio.run(validate_public_url("https://example.com/path"))


def test_unresolvable_host_rejected(monkeypatch):
    def boom(*args, **kwargs):
        raise socket.gaierror("no such host")

    monkeypatch.setattr(socket, "getaddrinfo", boom)
    with pytest.raises(UnsafeURLError):
        asyncio.run(validate_public_url("http://nope.invalid"))


def test_bad_shape_rejected_before_dns():
    with pytest.raises(UnsafeURLError):
        asyncio.run(validate_public_url("ftp://example.com"))


BLOCKED_NETS = [
    ipaddress.ip_network(n)
    for n in [
        "0.0.0.0/8",
        "10.0.0.0/8",
        "100.64.0.0/10",
        "127.0.0.0/8",
        "169.254.0.0/16",
        "172.16.0.0/12",
        "192.168.0.0/16",
        "224.0.0.0/4",
        "240.0.0.0/4",
        "::1/128",
        "fc00::/7",
        "fe80::/10",
        "ff00::/8",
    ]
]


@st.composite
def ip_in_blocked_net(draw):
    net = draw(st.sampled_from(BLOCKED_NETS))
    offset = draw(st.integers(0, net.num_addresses - 1))
    return net[offset]


@given(ip_in_blocked_net())
def test_any_ip_in_blocked_range_is_rejected(ip):
    assert _is_blocked(ip) is True


@given(st.text())
def test_get_host_only_raises_unsafe_url_error(s):
    try:
        _get_host(s)
    except UnsafeURLError:
        pass


async def test_dns_timeout_is_unsafe(monkeypatch):
    async def slow(*args, **kwargs):
        await asyncio.sleep(10)

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", slow)
    monkeypatch.setattr(ssrf, "DNS_TIMEOUT", 0.01)
    with pytest.raises(UnsafeURLError, match="cannot resolve host"):
        await validate_public_url("https://example.com")


async def test_dns_failure_is_unsafe(monkeypatch):
    async def boom(*args, **kwargs):
        raise socket.gaierror("no such host")

    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", boom)
    with pytest.raises(UnsafeURLError, match="cannot resolve host"):
        await validate_public_url("https://example.com")
