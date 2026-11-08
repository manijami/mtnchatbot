"""Settings, read once from the environment. Secrets are never logged or echoed."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

MIN_TOKEN_LENGTH = 32


class ConfigError(RuntimeError):
    """Raised at startup when the service cannot run safely."""


def _int(name: str, default: int, minimum: int = 0) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigError(f"{name} must be an integer") from exc
    if value < minimum:
        raise ConfigError(f"{name} must be >= {minimum}")
    return value


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    token: str
    data_dir: Path
    templates_dir: Path
    logo_dir: Path
    host: str
    port: int
    retention_days: int
    convert_timeout_s: int
    max_file_bytes: int
    preview_image: bool

    def __repr__(self) -> str:  # never print the token
        return f"Settings(data_dir={self.data_dir}, templates_dir={self.templates_dir}, port={self.port})"


def load_settings() -> Settings:
    token = os.environ.get("MTN_OFFICE_MCP_TOKEN", "")
    if len(token) < MIN_TOKEN_LENGTH:
        raise ConfigError(
            f"MTN_OFFICE_MCP_TOKEN must be set to at least {MIN_TOKEN_LENGTH} characters"
        )
    return Settings(
        token=token,
        data_dir=Path(os.environ.get("OFFICE_MCP_DATA_DIR", "/data")),
        templates_dir=Path(os.environ.get("OFFICE_MCP_TEMPLATES_DIR", "/app/templates")),
        logo_dir=Path(os.environ.get("OFFICE_MCP_LOGO_DIR", "/app/brand/logo")),
        host=os.environ.get("OFFICE_MCP_HOST", "0.0.0.0"),
        port=_int("OFFICE_MCP_PORT", 8000, minimum=1),
        # 0 keeps files until LibreChat deletes them; set to match LibreChat file retention.
        retention_days=_int("OFFICE_MCP_RETENTION_DAYS", 0),
        convert_timeout_s=_int("OFFICE_MCP_CONVERT_TIMEOUT", 60, minimum=5),
        max_file_bytes=_int("OFFICE_MCP_MAX_FILE_BYTES", 20 * 1024 * 1024, minimum=1024),
        # Off by default: MCP images are forwarded to the model, and text-only models reject them.
        preview_image=_bool("OFFICE_MCP_PREVIEW_IMAGE", False),
    )
