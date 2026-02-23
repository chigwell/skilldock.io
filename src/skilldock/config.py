from __future__ import annotations

import json
import os
import stat
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from platformdirs import user_config_path

DEFAULT_OPENAPI_URL = "https://api.skilldock.io/openapi.json"
DEFAULT_TIMEOUT_S = 30.0


@dataclass(frozen=True)
class Config:
    openapi_url: str = DEFAULT_OPENAPI_URL
    base_url: str | None = None
    token: str | None = None
    refresh_token: str | None = None
    token_expires_at: float | None = None  # epoch seconds (optional; JWT exp is preferred)
    timeout_s: float = DEFAULT_TIMEOUT_S
    auth_header: str | None = None  # e.g. "Authorization" or "X-API-Key"
    auth_scheme: str | None = None  # e.g. "Bearer" (only used with auth_header)


def config_path(path_override: str | Path | None = None) -> Path:
    if path_override is not None:
        return Path(path_override).expanduser()
    if env := os.getenv("SKILLDOCK_CONFIG_PATH"):
        return Path(env).expanduser()
    return user_config_path("skilldock") / "config.json"


def load_config(path_override: str | Path | None = None) -> Config:
    path = config_path(path_override)
    if not path.exists():
        return Config()

    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return Config()

    allowed = {f.name for f in Config.__dataclass_fields__.values()}  # type: ignore[attr-defined]
    filtered: dict[str, Any] = {k: v for k, v in raw.items() if k in allowed}
    return Config(**filtered)  # type: ignore[arg-type]


def save_config(cfg: Config, path_override: str | Path | None = None) -> Path:
    path = config_path(path_override)
    path.parent.mkdir(parents=True, exist_ok=True)

    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(asdict(cfg), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)

    # Best-effort permissions hardening (mainly for tokens).
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass

    return path


def redact_token(token: str | None) -> str | None:
    if not token:
        return token
    if len(token) <= 10:
        return token[:2] + "..." + token[-2:]
    return token[:6] + "..." + token[-4:]
