"""
Unit tests for rate limiter helpers.
"""

from types import SimpleNamespace

from api.core.rate_limiter import _get_client_ip


class _DummyRequest:
    def __init__(
        self, headers: dict[str, str] | None = None, client_host: str | None = None
    ) -> None:
        self.headers = headers or {}
        self.client = SimpleNamespace(host=client_host) if client_host else None


def test_get_client_ip_prefers_forwarded_for() -> None:
    request = _DummyRequest(headers={"x-forwarded-for": "203.0.113.10, 10.0.0.1"})
    assert _get_client_ip(request) == "203.0.113.10"


def test_get_client_ip_falls_back_to_real_ip() -> None:
    request = _DummyRequest(headers={"x-real-ip": "198.51.100.7"})
    assert _get_client_ip(request) == "198.51.100.7"


def test_get_client_ip_uses_client_host() -> None:
    request = _DummyRequest(client_host="192.0.2.55")
    assert _get_client_ip(request) == "192.0.2.55"


def test_get_client_ip_unknown_when_missing() -> None:
    request = _DummyRequest()
    assert _get_client_ip(request) == "unknown"
