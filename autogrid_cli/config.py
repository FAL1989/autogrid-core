"""Configuration handling for the AutoGrid CLI."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import tomllib

DEFAULT_API_URL = "http://localhost:8000"
CONFIG_DIR = Path.home() / ".config" / "autogrid"
CONFIG_PATH = CONFIG_DIR / "config.toml"


@dataclass
class Settings:
    api_url: str
    access_token: str | None
    refresh_token: str | None
    config_path: Path
    json_output: bool
    token_source: str
    store: "ConfigStore"


class ConfigStore:
    """Simple TOML-backed config store."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or CONFIG_PATH
        self.data: dict[str, Any] = {}

    def load(self) -> "ConfigStore":
        if not self.path.exists():
            self.data = {}
            return self
        content = self.path.read_text()
        if content.strip():
            self.data = tomllib.loads(content)
        else:
            self.data = {}
        return self

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        content = _dump_toml(self.data)
        self.path.write_text(content)
        os.chmod(self.path, 0o600)

    def get(self, section: str, key: str, default: Any | None = None) -> Any | None:
        return self.data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value: Any | None) -> None:
        self.data.setdefault(section, {})
        if value is None:
            self.data[section].pop(key, None)
            if not self.data[section]:
                self.data.pop(section, None)
            return
        self.data[section][key] = value

    def set_api_url(self, api_url: str) -> None:
        self.set("api", "url", api_url)

    def set_tokens(self, access_token: str, refresh_token: str) -> None:
        self.set("auth", "access_token", access_token)
        self.set("auth", "refresh_token", refresh_token)

    def clear_tokens(self) -> None:
        self.set("auth", "access_token", None)
        self.set("auth", "refresh_token", None)


def load_settings(api_url_override: str | None, json_output: bool) -> Settings:
    store = ConfigStore().load()

    api_url = store.get("api", "url") or DEFAULT_API_URL
    env_api_url = os.getenv("AUTOGRID_API_URL")
    if env_api_url:
        api_url = env_api_url
    if api_url_override:
        api_url = api_url_override

    access_token = store.get("auth", "access_token")
    refresh_token = store.get("auth", "refresh_token")
    token_source = "config"

    env_token = os.getenv("AUTOGRID_TOKEN")
    if env_token:
        access_token = env_token
        refresh_token = None
        token_source = "env"

    return Settings(
        api_url=api_url,
        access_token=access_token,
        refresh_token=refresh_token,
        config_path=store.path,
        json_output=json_output,
        token_source=token_source,
        store=store,
    )


def _dump_toml(data: dict[str, Any]) -> str:
    lines: list[str] = []
    for section in ("api", "auth"):
        values = data.get(section)
        if not isinstance(values, dict) or not values:
            continue
        lines.append(f"[{section}]")
        for key, value in values.items():
            if value is None:
                continue
            escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
        lines.append("")
    if not lines:
        return ""
    return "\n".join(lines).rstrip() + "\n"
