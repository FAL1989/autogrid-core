"""HTTP client for the AutoGrid CLI."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import httpx

from autogrid_cli.config import Settings


@dataclass
class ApiError(Exception):
    status_code: int
    detail: str


class ApiClient:
    """HTTP client with optional token refresh support."""

    def __init__(self, settings: Settings) -> None:
        base_url = settings.api_url.rstrip("/")
        if base_url.endswith("/api/v1"):
            base_url = base_url[: -len("/api/v1")]
        self.base_url = base_url
        self.profile = settings.profile
        self.access_token = settings.access_token
        self.refresh_token = settings.refresh_token
        self.persist_tokens = settings.token_source == "config"
        self.store = settings.store
        self._client = httpx.Client(timeout=30.0)

    def __enter__(self) -> "ApiClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def request(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> Any:
        response = self._request_once(method, path, json_body=json_body, params=params)
        if response.status_code == 401 and self.refresh_token:
            self._refresh_tokens()
            response = self._request_once(method, path, json_body=json_body, params=params)
        return self._handle_response(response)

    def request_raw(
        self,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        response = self._request_once(method, path, params=params)
        if response.status_code == 401 and self.refresh_token:
            self._refresh_tokens()
            response = self._request_once(method, path, params=params)
        if response.status_code >= 400:
            raise ApiError(response.status_code, _extract_detail(response))
        return response

    def _request_once(
        self,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        params: dict[str, Any] | None = None,
    ) -> httpx.Response:
        url = self._build_url(path)
        headers = {}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        return self._client.request(
            method,
            url,
            json=json_body,
            params=params,
            headers=headers,
        )

    def _build_url(self, path: str) -> str:
        if not path.startswith("/"):
            path = f"/{path}"
        return f"{self.base_url}{path}"

    def _refresh_tokens(self) -> None:
        if not self.refresh_token:
            return
        response = self._client.post(
            self._build_url("/auth/refresh"),
            json={"refresh_token": self.refresh_token},
        )
        if response.status_code >= 400:
            raise ApiError(response.status_code, _extract_detail(response))
        payload = response.json()
        self.access_token = payload.get("access_token")
        self.refresh_token = payload.get("refresh_token")
        if self.persist_tokens and self.access_token and self.refresh_token:
            self.store.set_profile_tokens(
                self.profile, self.access_token, self.refresh_token
            )
            self.store.save()

    @staticmethod
    def _handle_response(response: httpx.Response) -> Any:
        if response.status_code >= 400:
            raise ApiError(response.status_code, _extract_detail(response))
        if response.status_code == 204:
            return None
        return response.json()


def _extract_detail(response: httpx.Response) -> str:
    try:
        payload = response.json()
    except ValueError:
        return response.text.strip() or f"HTTP {response.status_code}"

    if isinstance(payload, dict):
        detail = payload.get("detail") or payload.get("message")
        if isinstance(detail, (dict, list)):
            return str(detail)
        if detail:
            return str(detail)
    return str(payload)
