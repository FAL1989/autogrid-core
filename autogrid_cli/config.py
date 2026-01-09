"""Configuration handling for the AutoGrid CLI."""

from __future__ import annotations

import os
import sys
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

DEFAULT_API_URL = "http://localhost:8000"
DEFAULT_PROFILE = "default"


def _default_config_path() -> Path:
    env_path = os.getenv("AUTOGRID_CONFIG_FILE")
    if env_path:
        return Path(env_path).expanduser()

    xdg_config_home = os.getenv("XDG_CONFIG_HOME")
    if xdg_config_home:
        return Path(xdg_config_home) / "autogrid" / "config.toml"

    if sys.platform == "win32":
        appdata = os.getenv("APPDATA")
        base = Path(appdata) if appdata else Path.home()
        return base / "autogrid" / "config.toml"

    if sys.platform == "darwin":
        return (
            Path.home() / "Library" / "Application Support" / "autogrid" / "config.toml"
        )

    return Path.home() / ".config" / "autogrid" / "config.toml"


@dataclass
class Settings:
    profile: str
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
        self.path = path or _default_config_path()
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

    def get_active_profile(self) -> str:
        value = self.get("cli", "profile")
        if isinstance(value, str) and value:
            return value
        return DEFAULT_PROFILE

    def set_active_profile(self, profile: str) -> None:
        self.set("cli", "profile", profile)

    def get_profile_data(self, profile: str) -> dict[str, Any]:
        profiles = self.data.get("profile")
        if isinstance(profiles, dict):
            profile_data = profiles.get(profile)
            if isinstance(profile_data, dict):
                return profile_data
        return {}

    def list_profiles(self) -> list[str]:
        profiles = self.data.get("profile")
        if not isinstance(profiles, dict):
            return []
        return sorted(
            [
                name
                for name, value in profiles.items()
                if isinstance(name, str) and isinstance(value, dict)
            ]
        )

    def get_profile_api_url(self, profile: str) -> str | None:
        profile_url = self.get_profile_data(profile).get("api_url")
        if isinstance(profile_url, str) and profile_url.strip():
            return profile_url

        legacy_url = self.get("api", "url")
        if isinstance(legacy_url, str) and legacy_url.strip():
            return legacy_url

        return None

    def set_profile_api_url(self, profile: str, api_url: str) -> None:
        self.data.setdefault("profile", {})
        if not isinstance(self.data["profile"], dict):
            self.data["profile"] = {}
        self.data["profile"].setdefault(profile, {})
        if not isinstance(self.data["profile"][profile], dict):
            self.data["profile"][profile] = {}
        self.data["profile"][profile]["api_url"] = api_url

    def get_profile_tokens(self, profile: str) -> tuple[str | None, str | None]:
        profile_data = self.get_profile_data(profile)
        access = profile_data.get("access_token")
        refresh = profile_data.get("refresh_token")
        if isinstance(access, str) or isinstance(refresh, str):
            return (
                access if isinstance(access, str) else None,
                refresh if isinstance(refresh, str) else None,
            )

        legacy_access = self.get("auth", "access_token")
        legacy_refresh = self.get("auth", "refresh_token")
        return (
            legacy_access if isinstance(legacy_access, str) else None,
            legacy_refresh if isinstance(legacy_refresh, str) else None,
        )

    def set_profile_tokens(
        self, profile: str, access_token: str, refresh_token: str
    ) -> None:
        self.data.setdefault("profile", {})
        if not isinstance(self.data["profile"], dict):
            self.data["profile"] = {}
        self.data["profile"].setdefault(profile, {})
        if not isinstance(self.data["profile"][profile], dict):
            self.data["profile"][profile] = {}
        self.data["profile"][profile]["access_token"] = access_token
        self.data["profile"][profile]["refresh_token"] = refresh_token

    def clear_profile_tokens(self, profile: str) -> None:
        profile_data = self.get_profile_data(profile)
        if profile_data:
            profile_data.pop("access_token", None)
            profile_data.pop("refresh_token", None)

        legacy_auth = self.data.get("auth")
        if isinstance(legacy_auth, dict):
            legacy_auth.pop("access_token", None)
            legacy_auth.pop("refresh_token", None)
            if not legacy_auth:
                self.data.pop("auth", None)


def load_settings(
    api_url_override: str | None, json_output: bool, profile_override: str | None = None
) -> Settings:
    store = ConfigStore().load()

    profile = (
        profile_override or os.getenv("AUTOGRID_PROFILE") or store.get_active_profile()
    )
    api_url = store.get_profile_api_url(profile) or DEFAULT_API_URL
    env_api_url = os.getenv("AUTOGRID_API_URL")
    if env_api_url:
        api_url = env_api_url
    if api_url_override:
        api_url = api_url_override

    access_token, refresh_token = store.get_profile_tokens(profile)
    token_source = "config"

    env_token = os.getenv("AUTOGRID_TOKEN")
    if env_token:
        access_token = env_token
        refresh_token = None
        token_source = "env"

    return Settings(
        profile=profile,
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

    cli = data.get("cli")
    if isinstance(cli, dict) and cli:
        lines.append("[cli]")
        for key, value in cli.items():
            if value is None:
                continue
            escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
            lines.append(f'{key} = "{escaped}"')
        lines.append("")

    profiles = data.get("profile")
    if isinstance(profiles, dict):
        for name, values in profiles.items():
            if not isinstance(name, str) or not isinstance(values, dict) or not values:
                continue
            lines.append(f"[profile.{name}]")
            for key, value in values.items():
                if value is None:
                    continue
                escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
                lines.append(f'{key} = "{escaped}"')
            lines.append("")

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
