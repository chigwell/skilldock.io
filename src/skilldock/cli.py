from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import textwrap
import time
import webbrowser
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, quote, urlsplit, urlunsplit

from ._version import __version__
from .client import AuthRequiredError, OperationNotFoundError, SkilldockClient, SkilldockError, SkilldockHTTPError
from .config import DEFAULT_OPENAPI_URL, Config, load_config, redact_token, save_config
from .local_skills import ApiReleaseRepository, LocalSkillManager, parse_skill_ref
from .skill_package import SkillPackageError, package_skill


def _jsonish(v: str) -> Any:
    v = v.strip()
    if v == "":
        return ""
    try:
        return json.loads(v)
    except json.JSONDecodeError:
        return v


def _parse_kv(s: str) -> tuple[str, Any]:
    if "=" not in s:
        raise ValueError("Expected key=value")
    k, v = s.split("=", 1)
    return k, _jsonish(v)


def _load_json_arg(s: str) -> Any:
    s = s.strip()
    if s.startswith("@"):
        path = Path(s[1:]).expanduser()
        return json.loads(path.read_text(encoding="utf-8"))
    return json.loads(s)


def _load_files(kvs: list[str]) -> dict[str, Any]:
    files: dict[str, Any] = {}
    for kv in kvs:
        k, v = _parse_kv(kv)
        if not isinstance(v, str) or not v.startswith("@"):
            raise ValueError("For --file, value must be like name=@/path/to/file")
        path = Path(v[1:]).expanduser()
        data = path.read_bytes()
        ctype, _ = mimetypes.guess_type(str(path))
        files[k] = (path.name, data, ctype or "application/octet-stream")
    return files


def _load_headers(kvs: list[str]) -> dict[str, str]:
    headers: dict[str, str] = {}
    for kv in kvs:
        if ":" not in kv:
            raise ValueError("Expected Header: value")
        k, v = kv.split(":", 1)
        headers[k.strip()] = v.strip()
    return headers


def _merge_cfg(base: Config, args: argparse.Namespace) -> Config:
    # Env overrides config; CLI overrides both.
    openapi_url = getattr(args, "openapi_url", None) or os.getenv("SKILLDOCK_OPENAPI_URL") or base.openapi_url
    base_url = getattr(args, "base_url", None) or os.getenv("SKILLDOCK_BASE_URL") or base.base_url

    # Convenience: if the user overrides base_url but did not override openapi_url, keep them aligned.
    # This helps "skilldock ops/call" behave intuitively against non-default APIs.
    openapi_url_explicit = getattr(args, "openapi_url", None) is not None or os.getenv("SKILLDOCK_OPENAPI_URL") is not None
    base_url_explicit = getattr(args, "base_url", None) is not None or os.getenv("SKILLDOCK_BASE_URL") is not None
    if base_url_explicit and not openapi_url_explicit and base.openapi_url == DEFAULT_OPENAPI_URL and base_url:
        openapi_url = f"{base_url.rstrip('/')}/openapi.json"

    token = getattr(args, "token", None) or os.getenv("SKILLDOCK_TOKEN") or base.token
    timeout_s = getattr(args, "timeout_s", None) or os.getenv("SKILLDOCK_TIMEOUT_S") or base.timeout_s
    try:
        timeout_s_f = float(timeout_s)
    except (TypeError, ValueError):
        timeout_s_f = base.timeout_s

    refresh_token = base.refresh_token
    token_expires_at = base.token_expires_at
    if token != base.token:
        refresh_token = None
        token_expires_at = None

    return Config(
        openapi_url=openapi_url,
        base_url=base_url,
        token=token,
        refresh_token=refresh_token,
        token_expires_at=token_expires_at,
        timeout_s=timeout_s_f,
        auth_header=base.auth_header,
        auth_scheme=base.auth_scheme,
    )


def _decode_jwt_unverified(token: str) -> dict[str, Any] | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload_b64 = parts[1]
    # base64url padding
    payload_b64 += "=" * (-len(payload_b64) % 4)
    try:
        data = base64.urlsafe_b64decode(payload_b64.encode("ascii"))
        obj = json.loads(data.decode("utf-8"))
        return obj if isinstance(obj, dict) else None
    except Exception:
        return None


def _jwt_exp_unverified(token: str) -> float | None:
    payload = _decode_jwt_unverified(token)
    if not payload:
        return None
    exp = payload.get("exp")
    if isinstance(exp, (int, float)):
        return float(exp)
    return None


def _is_token_expired(token: str, *, now: float | None = None, skew_s: float = 30.0) -> bool:
    exp = _jwt_exp_unverified(token)
    if exp is None:
        return False
    now_ts = time.time() if now is None else now
    return exp <= (now_ts + skew_s)


def _require_fresh_token(token: str) -> None:
    if not _is_token_expired(token):
        return
    exp = _jwt_exp_unverified(token)
    exp_s = "unknown"
    if exp is not None:
        exp_s = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(exp))
    raise SkilldockError(f"Token is expired (exp={exp_s}). Run `skilldock auth login` again.")


def _extract_token_from_text(text: str) -> str | None:
    t = text.strip()
    if t.startswith("http://") or t.startswith("https://"):
        u = urlsplit(t)
        q = parse_qs(u.query)
        frag = parse_qs(u.fragment)
        for key in ("token", "id_token", "access_token", "jwt"):
            if key in frag and frag[key]:
                return frag[key][0]
            if key in q and q[key]:
                return q[key][0]
        return None
    return t if t else None


def _origin_from_url(url: str) -> str | None:
    try:
        parts = urlsplit(url)
    except Exception:
        return None
    if not parts.scheme or not parts.netloc:
        return None
    return urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")


def _normalize_homepage_url(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    if len(cleaned) > 2048:
        raise SkilldockError("--homepage-url must be <= 2048 characters.")
    try:
        parts = urlsplit(cleaned)
    except Exception as e:
        raise SkilldockError("--homepage-url must be a valid URL.") from e
    if parts.scheme not in ("http", "https"):
        raise SkilldockError("--homepage-url must use http/https.")
    if not parts.netloc:
        raise SkilldockError("--homepage-url must include a host.")
    return cleaned


def _unwrap_success_envelope(obj: Any) -> Any:
    """
    Supports APIs that wrap responses as:
      {"success": true, "data": {...}}
      {"success": false, "error": {...}}
    """
    if not isinstance(obj, dict):
        return obj
    if obj.get("success") is True and "data" in obj:
        return obj.get("data")
    if obj.get("success") is False and "error" in obj:
        raise SkilldockError(f"API error: {obj.get('error')}")
    return obj


def _print_table(rows: list[list[str]]) -> None:
    if not rows:
        return
    widths = [0] * len(rows[0])
    for r in rows:
        for i, c in enumerate(r):
            widths[i] = max(widths[i], len(c))
    for r in rows:
        line = "  ".join(c.ljust(widths[i]) for i, c in enumerate(r))
        print(line.rstrip())


def _as_int_stat(v: Any) -> int:
    if isinstance(v, bool):
        return 0
    if isinstance(v, int):
        return max(v, 0)
    return 0


def _extract_download_stats(obj: Any) -> dict[str, int]:
    if not isinstance(obj, dict):
        return {"total": 0, "last_week": 0, "last_month": 0}
    return {
        "total": _as_int_stat(obj.get("total")),
        "last_week": _as_int_stat(obj.get("last_week")),
        "last_month": _as_int_stat(obj.get("last_month")),
    }


def _extract_sale_summary(obj: Any) -> dict[str, Any]:
    if not isinstance(obj, dict):
        return {
            "is_for_sale": False,
            "selling_description_md": "",
            "price_usd": "0.00",
            "sold_total": 0,
            "can_buy": False,
        }
    return {
        "is_for_sale": bool(obj.get("is_for_sale")),
        "selling_description_md": str(obj.get("selling_description_md", "")),
        "price_usd": str(obj.get("price_usd", "0.00")),
        "sold_total": _as_int_stat(obj.get("sold_total")),
        "can_buy": bool(obj.get("can_buy")),
    }


def _extract_access_summary(obj: Any) -> dict[str, bool]:
    if not isinstance(obj, dict):
        return {
            "can_view_full_content": False,
            "is_owner": False,
            "is_buyer": False,
            "can_buy": False,
        }
    return {
        "can_view_full_content": bool(obj.get("can_view_full_content")),
        "is_owner": bool(obj.get("is_owner")),
        "is_buyer": bool(obj.get("is_buyer")),
        "can_buy": bool(obj.get("can_buy")),
    }


def _extract_author_summary(obj: Any) -> tuple[str, str, str]:
    if not isinstance(obj, dict):
        return "", "", ""
    author = obj.get("author")
    if not isinstance(author, dict):
        return "", "", ""
    user_id = author.get("user_id")
    display_name = author.get("display_name")
    google_picture = author.get("google_picture")
    return (
        str(user_id).strip() if user_id is not None else "",
        str(display_name).strip() if display_name is not None else "",
        str(google_picture).strip() if google_picture is not None else "",
    )


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="skilldock",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="SkillDock API client (OpenAPI-driven).",
        epilog=textwrap.dedent(
            """\
            Environment variables:
              SKILLDOCK_OPENAPI_URL, SKILLDOCK_BASE_URL, SKILLDOCK_TOKEN, SKILLDOCK_TIMEOUT_S
            """
        ),
    )

    def _add_runtime_overrides(parser: argparse.ArgumentParser) -> None:
        # These flags are available both before and after subcommands for convenience, e.g.:
        #   skilldock --base-url https://api.skilldock.io auth login
        #   skilldock auth login --base-url https://api.skilldock.io
        parser.add_argument("--openapi-url", help="OpenAPI spec URL or local path")
        parser.add_argument("--base-url", help="API base URL (overrides spec servers)")
        parser.add_argument("--token", help="Auth token (overrides config/env)")
        parser.add_argument("--timeout-s", type=float, help="HTTP timeout in seconds")

    _add_runtime_overrides(p)
    p.add_argument("--version", action="version", version=f"skilldock {__version__}")

    sub = p.add_subparsers(dest="cmd", required=True)

    # config
    cfg = sub.add_parser("config", help="Manage local config")
    cfg_sub = cfg.add_subparsers(dest="subcmd", required=True)
    cfg_sub.add_parser("path", help="Print config path")
    cfg_sub.add_parser("show", help="Show config (token redacted)")

    cfg_set = cfg_sub.add_parser("set", help="Set config fields")
    cfg_set.add_argument("--openapi-url")
    cfg_set.add_argument("--base-url")
    cfg_set.add_argument("--token")
    cfg_set.add_argument("--timeout-s", type=float)
    cfg_set.add_argument("--auth-header", help='Auth header name, e.g. "Authorization"')
    cfg_set.add_argument("--auth-scheme", help='Auth scheme, e.g. "Bearer" (optional)')

    # auth
    auth = sub.add_parser("auth", help="Authentication helpers")
    auth_sub = auth.add_subparsers(dest="subcmd", required=True)
    auth_login = auth_sub.add_parser("login", help="Open browser login URL and store API access token (polling)")
    _add_runtime_overrides(auth_login)
    auth_login.add_argument("--no-open", action="store_true", help="Do not open the browser automatically")
    auth_login.add_argument(
        "--poll-timeout-s",
        type=float,
        default=None,
        help="How long to wait for approval (default: server expires_in or 600s)",
    )
    auth_login.add_argument(
        "--poll-interval-s",
        type=float,
        default=None,
        help="Polling interval override (default: server poll_interval_s or 2s)",
    )
    # Backwards-compat flags from the previous localhost-based flow (ignored).
    auth_login.add_argument("--redirect-uri", help="Deprecated/ignored (handled by backend)", default=None)
    auth_sub.add_parser("status", help="Show whether a token is configured")
    auth_set = auth_sub.add_parser("set-token", help="Store a token (or paste redirect URL containing token=...)")
    auth_set.add_argument("token_or_url")
    auth_sub.add_parser("clear", help="Remove stored token")
    auth_sub.add_parser("inspect", help="Decode JWT payload (no verification)")

    # tokens
    tok = sub.add_parser("tokens", help="Manage personal API tokens")
    tok_sub = tok.add_subparsers(dest="subcmd", required=True)

    tok_create = tok_sub.add_parser("create", help="Create a personal API token")
    _add_runtime_overrides(tok_create)
    tok_create.add_argument("--scope", action="append", default=[], help="Token scope (repeatable)")
    tok_create.add_argument("--expires-in-days", type=int, help="Token expiry in days (1..365)")
    tok_create.add_argument("--save", action="store_true", help="Save the created token as the default CLI token")
    tok_create.add_argument("--json", action="store_true", help="Output JSON")

    tok_list = tok_sub.add_parser("list", help="List your personal API tokens")
    _add_runtime_overrides(tok_list)
    tok_list.add_argument("--page", type=int)
    tok_list.add_argument("--per-page", type=int)
    tok_list.add_argument("--json", action="store_true", help="Output JSON")

    tok_revoke = tok_sub.add_parser("revoke", help="Revoke a personal API token")
    _add_runtime_overrides(tok_revoke)
    tok_revoke.add_argument("token_id", help="Token id to revoke")
    tok_revoke.add_argument("--json", action="store_true", help="Output JSON")

    # spec/ops
    spec = sub.add_parser("ops", help="List operations from the OpenAPI spec")
    _add_runtime_overrides(spec)
    spec.add_argument("--json", action="store_true", help="Output JSON")

    # call by operationId
    call = sub.add_parser("call", help="Call an API operationId from the OpenAPI spec")
    _add_runtime_overrides(call)
    call.add_argument("operation_id")
    call.add_argument("--param", action="append", default=[], help="Parameter key=value (repeatable)")
    call.add_argument("--json", dest="json_body", help="JSON body or @file.json")
    call.add_argument("--data", action="append", default=[], help="Form field key=value (repeatable)")
    call.add_argument("--file", action="append", default=[], help="Upload file name=@/path/to/file (repeatable)")
    call.add_argument("--header", action="append", default=[], help="Extra header 'Header: value' (repeatable)")
    call.add_argument("--no-auth", action="store_true", help="Do not send auth headers")
    call.add_argument("--raw", action="store_true", help="Print raw response text")

    # low-level request
    req = sub.add_parser("request", help="Low-level request by method + path (bypasses OpenAPI operationId)")
    _add_runtime_overrides(req)
    req.add_argument("method")
    req.add_argument("path")
    req.add_argument("--query", action="append", default=[], help="Query key=value (repeatable)")
    req.add_argument("--json", dest="json_body", help="JSON body or @file.json")
    req.add_argument("--data", action="append", default=[], help="Form field key=value (repeatable)")
    req.add_argument("--file", action="append", default=[], help="Upload file name=@/path/to/file (repeatable)")
    req.add_argument("--header", action="append", default=[], help="Extra header 'Header: value' (repeatable)")
    req.add_argument("--no-auth", action="store_true", help="Do not send auth headers")
    req.add_argument("--raw", action="store_true", help="Print raw response text")

    # skills (remote)
    skills = sub.add_parser("skills", help="Remote skill operations")
    skills_sub = skills.add_subparsers(dest="subcmd", required=True)

    skills_search = skills_sub.add_parser("search", help="Search skills (public + private when authenticated)")
    _add_runtime_overrides(skills_search)
    skills_search.add_argument("q", nargs="?", default=None, help="Search query")
    skills_search.add_argument("--namespace")
    skills_search.add_argument("--tag")
    skills_search.add_argument("--page", type=int)
    skills_search.add_argument("--per-page", type=int)
    skills_search.add_argument("--json", action="store_true", help="Output JSON")

    skills_get = skills_sub.add_parser("get", help="Get one skill (latest release metadata)")
    _add_runtime_overrides(skills_get)
    skills_get.add_argument("skill", help="Skill identifier in form namespace/slug")
    skills_get.add_argument("--json", action="store_true", help="Output JSON")

    skills_release = skills_sub.add_parser("release", help="Get one release by exact version")
    _add_runtime_overrides(skills_release)
    skills_release.add_argument("skill", help="Skill identifier in form namespace/slug")
    skills_release.add_argument("version", help="Exact release version")
    skills_release.add_argument("--json", action="store_true", help="Output JSON")

    skills_releases = skills_sub.add_parser("releases", help="List releases for a skill (paginated)")
    _add_runtime_overrides(skills_releases)
    skills_releases.add_argument("skill", help="Skill identifier in form namespace/slug")
    skills_releases.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    skills_releases.add_argument("--per-page", type=int, default=10, help="Page size (default: 10, max: 100)")
    skills_releases.add_argument("--json", action="store_true", help="Output JSON")

    skills_set_ton_wallet = skills_sub.add_parser("set-ton-wallet", help="Set TON payout wallet for current user")
    _add_runtime_overrides(skills_set_ton_wallet)
    skills_set_ton_wallet.add_argument("--ton-wallet-address", required=True)
    skills_set_ton_wallet.add_argument("--json", action="store_true", help="Output JSON")

    skills_set_price = skills_sub.add_parser("set-price", help="Set active sale price for a skill")
    _add_runtime_overrides(skills_set_price)
    skills_set_price.add_argument("skill", help="Skill identifier in form namespace/slug")
    skills_set_price.add_argument("--price-usd", required=True, help='Price in USD, e.g. "12.00"')
    skills_set_price.add_argument("--json", action="store_true", help="Output JSON")

    skills_set_commerce = skills_sub.add_parser("set-commerce", help="Set skill commerce flags and selling description")
    _add_runtime_overrides(skills_set_commerce)
    skills_set_commerce.add_argument("skill", help="Skill identifier in form namespace/slug")
    skills_set_commerce.add_argument("--is-for-sale", choices=("true", "false"), required=True)
    skills_set_commerce.add_argument("--visibility", choices=("public", "private"))
    skills_set_commerce.add_argument("--selling-description-md")
    skills_set_commerce.add_argument("--json", action="store_true", help="Output JSON")

    skills_buy = skills_sub.add_parser("buy", help="Create/reuse invoice and optionally poll until paid or expired")
    _add_runtime_overrides(skills_buy)
    skills_buy.add_argument("skill", help="Skill identifier in form namespace/slug")
    skills_buy.add_argument("--poll", action="store_true", help="Poll invoice status until paid or expired")
    skills_buy.add_argument("--poll-interval-s", type=float, default=3.0, help="Polling interval seconds (default: 3)")
    skills_buy.add_argument("--poll-timeout-s", type=float, default=1800.0, help="Polling timeout seconds (default: 1800)")
    skills_buy.add_argument("--json", action="store_true", help="Output JSON")

    skills_invoice = skills_sub.add_parser("invoice", help="Get invoice status by invoice id")
    _add_runtime_overrides(skills_invoice)
    skills_invoice.add_argument("invoice_id")
    skills_invoice.add_argument("--json", action="store_true", help="Output JSON")

    skills_sales = skills_sub.add_parser("sales", help="List paid sales for current user or one authored skill")
    _add_runtime_overrides(skills_sales)
    skills_sales.add_argument("--skill", help="Optional skill identifier in form namespace/slug")
    skills_sales.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    skills_sales.add_argument("--per-page", type=int, default=20, help="Page size (default: 20)")
    skills_sales.add_argument("--json", action="store_true", help="Output JSON")

    # skill (local + upload)
    skill = sub.add_parser("skill", help="Local skill packaging and upload")
    skill_sub = skill.add_subparsers(dest="subcmd", required=True)

    skill_verify = skill_sub.add_parser("verify", help="Verify and package a local skill folder")
    skill_verify.add_argument("path", nargs="?", default=".", help="Path to skill folder (default: .)")
    skill_verify.add_argument("--json", action="store_true", help="Output JSON")

    skill_upload = skill_sub.add_parser("upload", help="Upload a new skill release")
    _add_runtime_overrides(skill_upload)
    skill_upload.add_argument("--path", default=".", help="Path to skill folder (default: .)")
    skill_upload.add_argument("--namespace", required=True)
    skill_upload.add_argument("--slug", required=True)
    skill_upload.add_argument("--version", help="Release version (optional)")
    skill_upload.add_argument("--homepage-url", help="Homepage URL (optional, http/https)")
    skill_upload.add_argument(
        "--visibility",
        choices=("public", "private"),
        help="Release visibility (default: public)",
    )
    skill_upload.add_argument(
        "--dependency",
        action="append",
        default=[],
        help='Dependency entry (repeatable), e.g. "core/base-utils@^1.2.0" or "lint@>=2.0.0 <3.0.0"',
    )
    skill_upload.add_argument(
        "--dependencies-json",
        help="Dependencies JSON (array/map), or @path/to/file.json",
    )
    skill_upload.add_argument(
        "--create-namespace",
        action="store_true",
        help="If the namespace does not exist, create it as an org namespace and retry",
    )
    skill_upload.add_argument("--json", action="store_true", help="Output JSON")
    skill_upload.add_argument("--dry-run", action="store_true", help="Package and print info only (no network)")

    # local install / uninstall
    install = sub.add_parser(
        "install",
        aliases=["i"],
        help="Install or update a skill locally with recursive dependency resolution",
    )
    _add_runtime_overrides(install)
    install.add_argument("skill", help="Skill identifier in form namespace/slug or namespace/slug@version")
    install.add_argument("--version", help="Version or constraint (default: latest); cannot be combined with @version")
    install.add_argument(
        "--skills-dir",
        default="./skills",
        help="Local skills directory (default: ./skills)",
    )
    install.add_argument("--json", action="store_true", help="Output JSON")

    uninstall = sub.add_parser(
        "uninstall",
        aliases=["remove", "rm"],
        help="Remove a direct skill and reconcile dependencies locally",
    )
    _add_runtime_overrides(uninstall)
    uninstall.add_argument("skill", help="Skill identifier in form namespace/slug")
    uninstall.add_argument(
        "--skills-dir",
        default="./skills",
        help="Local skills directory (default: ./skills)",
    )
    uninstall.add_argument("--json", action="store_true", help="Output JSON")

    # namespaces
    ns = sub.add_parser("namespaces", help="Manage namespaces")
    ns_sub = ns.add_subparsers(dest="subcmd", required=True)

    ns_list = ns_sub.add_parser("list", help="List namespaces the current user is a member of")
    _add_runtime_overrides(ns_list)
    ns_list.add_argument("--page", type=int)
    ns_list.add_argument("--per-page", type=int)
    ns_list.add_argument("--json", action="store_true", help="Output JSON")

    ns_create = ns_sub.add_parser("create", help="Create an org namespace")
    _add_runtime_overrides(ns_create)
    ns_create.add_argument("slug", help="Namespace slug (e.g. myorg)")
    ns_create.add_argument("--json", action="store_true", help="Output JSON")

    # users
    users = sub.add_parser("users", help="User profile operations")
    users_sub = users.add_subparsers(dest="subcmd", required=True)

    users_get = users_sub.add_parser("get", help="Get user profile and authored skills")
    _add_runtime_overrides(users_get)
    users_get.add_argument("user_id", help="Author user id")
    users_get.add_argument("--page", type=int, default=1, help="Page number (default: 1)")
    users_get.add_argument("--per-page", type=int, default=20, help="Page size (default: 20)")
    users_get.add_argument("--json", action="store_true", help="Output JSON")

    return p


def _client_from_cfg(cfg: Config) -> SkilldockClient:
    return SkilldockClient(
        openapi_url=cfg.openapi_url,
        base_url=cfg.base_url,
        token=cfg.token,
        timeout_s=cfg.timeout_s,
        auth_header=cfg.auth_header,
        auth_scheme=cfg.auth_scheme,
    )


def cmd_config(args: argparse.Namespace) -> int:
    if args.subcmd == "path":
        from .config import config_path

        print(str(config_path()))
        return 0

    if args.subcmd == "show":
        cfg = load_config()
        d = cfg.__dict__.copy()
        d["token"] = redact_token(cfg.token)
        d["refresh_token"] = redact_token(cfg.refresh_token)
        print(json.dumps(d, indent=2, sort_keys=True))
        return 0

    if args.subcmd == "set":
        cfg = load_config()
        openapi_url = args.openapi_url or cfg.openapi_url
        base_url = args.base_url if args.base_url is not None else cfg.base_url
        token = args.token if args.token is not None else cfg.token
        timeout_s = args.timeout_s if args.timeout_s is not None else cfg.timeout_s
        auth_header = args.auth_header if args.auth_header is not None else cfg.auth_header
        auth_scheme = args.auth_scheme if args.auth_scheme is not None else cfg.auth_scheme

        refresh_token = cfg.refresh_token
        token_expires_at = cfg.token_expires_at
        if args.token is not None and args.token != cfg.token:
            refresh_token = None
            token_expires_at = _jwt_exp_unverified(token) if token else None

        new_cfg = Config(
            openapi_url=openapi_url,
            base_url=base_url,
            token=token,
            refresh_token=refresh_token,
            token_expires_at=token_expires_at,
            timeout_s=timeout_s,
            auth_header=auth_header,
            auth_scheme=auth_scheme,
        )
        path = save_config(new_cfg)
        print(f"Saved: {path}")
        return 0

    raise AssertionError("unreachable")


def cmd_auth(args: argparse.Namespace) -> int:
    if args.subcmd == "status":
        cfg = load_config()
        if not cfg.token:
            print("token: not set")
            return 0

        extra = ""
        exp = _jwt_exp_unverified(cfg.token)
        if exp is not None:
            extra = f" (exp={time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(exp))})"
        print(f"token: configured{extra}")
        return 0

    if args.subcmd == "clear":
        cfg = load_config()
        new_cfg = Config(
            openapi_url=cfg.openapi_url,
            base_url=cfg.base_url,
            token=None,
            refresh_token=None,
            token_expires_at=None,
            timeout_s=cfg.timeout_s,
            auth_header=cfg.auth_header,
            auth_scheme=cfg.auth_scheme,
        )
        save_config(new_cfg)
        print("Token cleared.")
        return 0

    if args.subcmd == "set-token":
        cfg = load_config()
        token = _extract_token_from_text(args.token_or_url)
        if not token:
            raise SkilldockError("Could not extract a token from the provided input.")
        token_expires_at = _jwt_exp_unverified(token)
        new_cfg = Config(
            openapi_url=cfg.openapi_url,
            base_url=cfg.base_url,
            token=token,
            refresh_token=None,
            token_expires_at=token_expires_at,
            timeout_s=cfg.timeout_s,
            auth_header=cfg.auth_header,
            auth_scheme=cfg.auth_scheme,
        )
        save_config(new_cfg)
        print("Token saved.")
        return 0

    if args.subcmd == "inspect":
        cfg = load_config()
        if not cfg.token:
            print("No token configured.")
            return 1
        payload = _decode_jwt_unverified(cfg.token)
        if payload is None:
            print("Token does not look like a JWT (or could not be decoded).")
            return 1
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    if args.subcmd == "login":
        cfg_file = load_config()
        cfg = _merge_cfg(cfg_file, args)

        base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
        if not base_url:
            raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")

        client = SkilldockClient(
            openapi_url=cfg.openapi_url,
            base_url=base_url,
            token=None,
            timeout_s=cfg.timeout_s,
        )
        try:
            resp = client.request(method="POST", path="/auth/cli/sessions", auth=False)
            data = _unwrap_success_envelope(resp.json())
        finally:
            client.close()

        session_id = data.get("session_id")
        auth_url = data.get("auth_url")
        expires_in = data.get("expires_in")
        poll_interval_s = data.get("poll_interval_s")

        if not isinstance(session_id, str) or not session_id:
            raise SkilldockError("Unexpected response from /auth/cli/sessions: missing session_id")
        if not isinstance(auth_url, str) or not auth_url.startswith(("http://", "https://")):
            raise SkilldockError("Unexpected response from /auth/cli/sessions: missing auth_url")

        print(auth_url)
        if not args.no_open:
            webbrowser.open(auth_url)
        print(f"Waiting for approval (session_id={session_id})...", file=sys.stderr)

        # Determine polling params.
        if isinstance(poll_interval_s, (int, float)):
            poll_interval = float(poll_interval_s)
        else:
            poll_interval = 2.0
        if args.poll_interval_s is not None:
            poll_interval = float(args.poll_interval_s)
        poll_interval = max(0.2, poll_interval)

        if isinstance(expires_in, (int, float)):
            default_timeout = float(expires_in)
        else:
            default_timeout = 600.0
        poll_timeout = float(args.poll_timeout_s) if args.poll_timeout_s is not None else default_timeout
        deadline = time.time() + max(1.0, poll_timeout)

        client = SkilldockClient(
            openapi_url=cfg.openapi_url,
            base_url=base_url,
            token=None,
            timeout_s=cfg.timeout_s,
        )
        try:
            while True:
                if time.time() > deadline:
                    raise SkilldockError("Timed out waiting for browser approval.")

                resp = client.request(method="GET", path=f"/auth/cli/sessions/{session_id}", auth=False)
                st = _unwrap_success_envelope(resp.json())
                status = st.get("status")

                if status == "pending":
                    time.sleep(poll_interval)
                    continue
                if status == "approved":
                    access_token = st.get("access_token")
                    if not isinstance(access_token, str) or not access_token:
                        raise SkilldockError("Session approved but access_token is missing.")

                    refresh_token = st.get("refresh_token")
                    if not isinstance(refresh_token, str):
                        refresh_token = None

                    expires_in = st.get("expires_in")
                    token_expires_at = _jwt_exp_unverified(access_token)
                    if token_expires_at is None and isinstance(expires_in, (int, float)):
                        token_expires_at = time.time() + float(expires_in)

                    # Keep the spec URL aligned with the base_url when the user is targeting a non-default API.
                    openapi_url_to_save = cfg_file.openapi_url
                    if (
                        getattr(args, "openapi_url", None) is None
                        and os.getenv("SKILLDOCK_OPENAPI_URL") is None
                        and cfg_file.openapi_url == DEFAULT_OPENAPI_URL
                    ):
                        openapi_url_to_save = f"{(cfg.base_url or base_url).rstrip('/')}/openapi.json"

                    new_cfg = Config(
                        openapi_url=openapi_url_to_save,
                        base_url=cfg.base_url or base_url,
                        token=access_token,
                        refresh_token=refresh_token,
                        token_expires_at=token_expires_at,
                        timeout_s=cfg_file.timeout_s,
                        auth_header=cfg_file.auth_header,
                        auth_scheme=cfg_file.auth_scheme,
                    )
                    save_config(new_cfg)
                    print("Token saved.")
                    return 0
                if status in ("denied", "expired"):
                    raise SkilldockError(f"Login {status}.")

                raise SkilldockError(f"Unexpected session status: {status!r}")
        finally:
            client.close()

    raise AssertionError("unreachable")


def cmd_tokens(args: argparse.Namespace) -> int:
    cfg_file = load_config()
    cfg = _merge_cfg(cfg_file, args)
    base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
    if not base_url:
        raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")
    if not cfg.token:
        raise SkilldockError("Missing token. Run `skilldock auth login` first.")
    _require_fresh_token(cfg.token)

    client = SkilldockClient(openapi_url=cfg.openapi_url, base_url=base_url, token=cfg.token, timeout_s=cfg.timeout_s)
    try:
        if args.subcmd == "create":
            body: dict[str, Any] = {}
            if args.scope:
                body["scopes"] = list(args.scope)
            if args.expires_in_days is not None:
                body["expires_in_days"] = int(args.expires_in_days)

            resp = client.request(method="POST", path="/v1/tokens", json_body=body or None, auth=True)
            data = _unwrap_success_envelope(resp.json())

            if args.json:
                print(json.dumps(data, indent=2, sort_keys=True))
                return 0

            token = data.get("token") if isinstance(data, dict) else None
            token_meta = data.get("token_meta") if isinstance(data, dict) else None
            if not isinstance(token, str) or not token:
                print(json.dumps(data, indent=2, sort_keys=True))
                return 0

            # Print token first for easy copy/paste.
            print(token)

            if isinstance(token_meta, dict):
                rows: list[list[str]] = [["FIELD", "VALUE"]]
                for k in (
                    "id",
                    "token_prefix",
                    "scopes",
                    "created_at",
                    "expires_at",
                    "revoked_at",
                    "last_used_at",
                ):
                    if k not in token_meta:
                        continue
                    v = token_meta.get(k)
                    if isinstance(v, list):
                        v = ",".join(str(x) for x in v)
                    rows.append([k, str(v)])
                _print_table(rows)

            if args.save:
                # Keep the spec URL aligned with the base_url when the user is targeting a non-default API.
                openapi_url_to_save = cfg_file.openapi_url
                if (
                    getattr(args, "openapi_url", None) is None
                    and os.getenv("SKILLDOCK_OPENAPI_URL") is None
                    and cfg_file.openapi_url == DEFAULT_OPENAPI_URL
                ):
                    openapi_url_to_save = f"{(cfg.base_url or base_url).rstrip('/')}/openapi.json"

                new_cfg = Config(
                    openapi_url=openapi_url_to_save,
                    base_url=cfg.base_url or base_url,
                    token=token,
                    refresh_token=None,
                    token_expires_at=_jwt_exp_unverified(token) if token else None,
                    timeout_s=cfg_file.timeout_s,
                    auth_header=cfg_file.auth_header,
                    auth_scheme=cfg_file.auth_scheme,
                )
                save_config(new_cfg)
                print("Token saved.", file=sys.stderr)
            else:
                print("Tip: save it with: skilldock auth set-token <token>", file=sys.stderr)

            return 0

        if args.subcmd == "list":
            params: dict[str, Any] = {}
            if args.page:
                params["page"] = args.page
            if args.per_page:
                params["per_page"] = args.per_page
            resp = client.request(method="GET", path="/v1/tokens", params=params or None, auth=True)
            data = _unwrap_success_envelope(resp.json())

            if args.json:
                print(json.dumps(data, indent=2, sort_keys=True))
                return 0

            items = data.get("items") if isinstance(data, dict) else None
            if not isinstance(items, list):
                print(json.dumps(data, indent=2, sort_keys=True))
                return 0

            rows: list[list[str]] = [["ID", "PREFIX", "SCOPES", "CREATED_AT", "EXPIRES_AT", "REVOKED_AT", "LAST_USED_AT"]]
            for it in items:
                if not isinstance(it, dict):
                    continue
                scopes = it.get("scopes")
                if isinstance(scopes, list):
                    scopes_s = ",".join(str(s) for s in scopes)
                else:
                    scopes_s = str(scopes or "")
                rows.append(
                    [
                        str(it.get("id", "")),
                        str(it.get("token_prefix", "")),
                        scopes_s,
                        str(it.get("created_at", "")),
                        str(it.get("expires_at", "")),
                        str(it.get("revoked_at", "")),
                        str(it.get("last_used_at", "")),
                    ]
                )
            _print_table(rows)
            return 0

        if args.subcmd == "revoke":
            resp = client.request(method="DELETE", path=f"/v1/tokens/{args.token_id}", auth=True)
            data = _unwrap_success_envelope(resp.json())

            if args.json:
                print(json.dumps(data, indent=2, sort_keys=True))
                return 0

            tok = data.get("token") if isinstance(data, dict) else None
            tid = None
            if isinstance(tok, dict) and "id" in tok:
                tid = tok.get("id")
            print(f"revoked: {tid if tid is not None else args.token_id}")
            return 0

        raise AssertionError("unreachable")
    finally:
        client.close()


def cmd_ops(args: argparse.Namespace) -> int:
    cfg_file = load_config()
    cfg = _merge_cfg(cfg_file, args)
    client = _client_from_cfg(cfg)
    try:
        ops = list(client.spec.operations.values())
        ops.sort(key=lambda o: (o.path, o.method, o.operation_id))
        if args.json:
            out = [
                {
                    "operation_id": o.operation_id,
                    "python_name": o.python_name,
                    "method": o.method,
                    "path": o.path,
                    "requires_auth": o.requires_auth,
                    "summary": o.summary,
                    "deprecated": o.deprecated,
                }
                for o in ops
            ]
            print(json.dumps(out, indent=2, sort_keys=True))
            return 0

        for o in ops:
            auth = "auth" if o.requires_auth else "no-auth"
            dep = " deprecated" if o.deprecated else ""
            summary = f" - {o.summary}" if o.summary else ""
            print(f"{o.python_name}\t{o.operation_id}\t{o.method.upper():<6}\t{o.path}\t[{auth}]{dep}{summary}")
        return 0
    finally:
        client.close()


def cmd_skills(args: argparse.Namespace) -> int:
    if args.subcmd == "search":
        cfg_file = load_config()
        cfg = _merge_cfg(cfg_file, args)
        base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
        if not base_url:
            raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")

        client = SkilldockClient(openapi_url=cfg.openapi_url, base_url=base_url, token=cfg.token, timeout_s=cfg.timeout_s)
        try:
            body: dict[str, Any] = {
                "query": args.q or "",
                "rewrite_query": True,
            }
            if args.per_page:
                body["max_num_results"] = args.per_page

            resp = client.request(method="POST", path="/v2/search", json_body=body, auth=True)
            data = _unwrap_success_envelope(resp.json())
        finally:
            client.close()

        if isinstance(data, dict):
            raw_items = data.get("items")
            if isinstance(raw_items, list):
                filtered_items: list[dict[str, Any]] = []
                for it in raw_items:
                    if not isinstance(it, dict):
                        continue
                    if args.namespace and str(it.get("namespace", "")) != args.namespace:
                        continue
                    if args.tag:
                        tags = it.get("tags") if isinstance(it.get("tags"), list) else []
                        if args.tag not in [str(t) for t in tags]:
                            continue
                    filtered_items.append(it)
                page = args.page if args.page and args.page > 0 else 1
                per_page = args.per_page if args.per_page and args.per_page > 0 else len(filtered_items) or 20
                start = (page - 1) * per_page
                end = start + per_page
                data["items"] = filtered_items[start:end]
                data["page"] = page
                data["per_page"] = per_page
                data["has_more"] = end < len(filtered_items)

        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0

        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0

        rows: list[list[str]] = [["SKILL", "TITLE", "UPDATED_AT", "PRICE_USD", "SOLD", "CAN_BUY", "TAGS", "LATEST_VERSIONS"]]
        for it in items:
            if not isinstance(it, dict):
                continue
            ns = str(it.get("namespace", ""))
            slug = str(it.get("slug", ""))
            title = str(it.get("title", ""))
            updated_at = str(it.get("updated_at", ""))
            tags = it.get("tags") if isinstance(it.get("tags"), list) else []
            tags_s = ",".join(str(t) for t in tags[:6])
            latest_releases = it.get("latest_releases") if isinstance(it.get("latest_releases"), list) else []
            versions: list[str] = []
            for rel in latest_releases[:5]:
                if isinstance(rel, dict) and isinstance(rel.get("version"), str):
                    v = rel.get("version", "").strip()
                    if v:
                        versions.append(v)
            versions_s = ",".join(versions)
            sale = _extract_sale_summary(it.get("sale"))
            author_id, _, _ = _extract_author_summary(it)
            skill_id = f"{ns}/{slug}"
            if author_id:
                skill_id = f"{skill_id} (u:{author_id})"
            rows.append(
                [
                    skill_id,
                    title,
                    updated_at,
                    str(sale["price_usd"]),
                    str(sale["sold_total"]),
                    "true" if bool(sale["can_buy"]) else "false",
                    tags_s,
                    versions_s,
                ]
            )
        _print_table(rows)
        return 0

    if args.subcmd == "get":
        cfg_file = load_config()
        cfg = _merge_cfg(cfg_file, args)
        base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
        if not base_url:
            raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")

        ref = parse_skill_ref(args.skill)
        skill_path = f"/v1/skills/{quote(ref.namespace, safe='')}/{quote(ref.slug, safe='')}"
        client = SkilldockClient(openapi_url=cfg.openapi_url, base_url=base_url, token=cfg.token, timeout_s=cfg.timeout_s)
        try:
            resp = client.request(method="GET", path=skill_path, auth=True)
            data = _unwrap_success_envelope(resp.json())
        finally:
            client.close()

        skill = data.get("skill") if isinstance(data, dict) and isinstance(data.get("skill"), dict) else data
        if not isinstance(skill, dict):
            skill = {}
        access = _extract_access_summary(skill.get("access"))
        sale = _extract_sale_summary(skill.get("sale"))
        owner_setup = skill.get("sale", {}).get("owner_setup") if isinstance(skill.get("sale"), dict) else None

        latest_release = skill.get("latest_release") if isinstance(skill.get("latest_release"), dict) else None
        latest_release_version = ""
        if latest_release and isinstance(latest_release.get("version"), str):
            latest_release_version = latest_release.get("version", "").strip()

        description_md = ""
        description_source = "empty"
        if latest_release and isinstance(latest_release.get("description_md"), str):
            candidate = latest_release.get("description_md", "")
            if candidate.strip():
                description_md = candidate
                description_source = "latest_release.description_md"
        if not description_md and isinstance(skill.get("description_md"), str):
            candidate = skill.get("description_md", "")
            if candidate.strip():
                description_md = candidate
                description_source = "skill.description_md"

        payload = {
            "skill": skill,
            "latest_release_version": latest_release_version,
            "description_md": description_md,
            "description_source": description_source,
            "download_stats": _extract_download_stats(skill.get("download_stats")),
            "first_release_created_at": (
                str(skill.get("first_release_created_at"))
                if skill.get("first_release_created_at") is not None
                else None
            ),
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        download_stats = payload["download_stats"]
        first_release_created_at = payload["first_release_created_at"] or "N/A"
        print(f"skill: {ref.key}")
        print(f"title: {str(skill.get('title', ''))}")
        author_id, author_name, author_picture = _extract_author_summary(skill)
        if author_id:
            print(f"author_user_id: {author_id}")
        if author_name:
            print(f"author_display_name: {author_name}")
        if author_picture:
            print(f"author_google_picture: {author_picture}")
        homepage_url = skill.get("homepage_url")
        if isinstance(homepage_url, str) and homepage_url.strip():
            print(f"homepage_url: {homepage_url.strip()}")
        print(f"latest_release: {latest_release_version}")
        print(f"created_at: {first_release_created_at}")
        print("access:")
        print(f"  can_view_full_content: {'true' if access['can_view_full_content'] else 'false'}")
        print(f"  is_owner: {'true' if access['is_owner'] else 'false'}")
        print(f"  is_buyer: {'true' if access['is_buyer'] else 'false'}")
        print(f"  can_buy: {'true' if access['can_buy'] else 'false'}")
        print("sale:")
        print(f"  is_for_sale: {'true' if sale['is_for_sale'] else 'false'}")
        print(f"  price_usd: {sale['price_usd']}")
        print(f"  sold_total: {sale['sold_total']}")
        print(f"  can_buy: {'true' if sale['can_buy'] else 'false'}")
        print("downloads:")
        print(f"  total: {download_stats['total']}")
        print(f"  last_week: {download_stats['last_week']}")
        print(f"  last_month: {download_stats['last_month']}")
        if isinstance(owner_setup, dict):
            print("owner_setup:")
            print(f"  status: {str(owner_setup.get('status', ''))}")
            missing = owner_setup.get("missing_requirements")
            if isinstance(missing, list):
                print(f"  missing_requirements: {','.join(str(x) for x in missing)}")
        print(f"description_source: {description_source}")
        if description_md:
            print("description_md:")
            print(description_md)
        return 0

    if args.subcmd == "release":
        cfg_file = load_config()
        cfg = _merge_cfg(cfg_file, args)
        base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
        if not base_url:
            raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")

        ref = parse_skill_ref(args.skill)
        skill_path = f"/v1/skills/{quote(ref.namespace, safe='')}/{quote(ref.slug, safe='')}"
        release_path = f"{skill_path}/releases/{quote(args.version, safe='')}"
        client = SkilldockClient(openapi_url=cfg.openapi_url, base_url=base_url, token=cfg.token, timeout_s=cfg.timeout_s)
        try:
            rel_resp = client.request(method="GET", path=release_path, auth=True)
            rel_data = _unwrap_success_envelope(rel_resp.json())
            release = rel_data.get("release") if isinstance(rel_data, dict) and isinstance(rel_data.get("release"), dict) else rel_data
            skill = rel_data.get("skill") if isinstance(rel_data, dict) and isinstance(rel_data.get("skill"), dict) else {}
            if not isinstance(release, dict):
                release = {}
            if not isinstance(skill, dict):
                skill = {}

            description_md = ""
            description_source = "empty"
            if isinstance(release.get("description_md"), str):
                candidate = release.get("description_md", "")
                if candidate.strip():
                    description_md = candidate
                    description_source = "release.description_md"

            # Backward-compat for older rows without release.description_md.
            if not description_md:
                skill_resp = client.request(method="GET", path=skill_path, auth=True)
                skill_data = _unwrap_success_envelope(skill_resp.json())
                fallback_skill = (
                    skill_data.get("skill")
                    if isinstance(skill_data, dict) and isinstance(skill_data.get("skill"), dict)
                    else skill_data
                )
                if isinstance(fallback_skill, dict) and isinstance(fallback_skill.get("description_md"), str):
                    candidate = fallback_skill.get("description_md", "")
                    if candidate.strip():
                        description_md = candidate
                        description_source = "skill.description_md"
        finally:
            client.close()

        payload = {
            "skill": skill,
            "release": release,
            "description_md": description_md,
            "description_source": description_source,
            "release_download_stats": _extract_download_stats(release.get("download_stats")),
            "download_stats": _extract_download_stats(skill.get("download_stats")),
            "first_release_created_at": (
                str(skill.get("first_release_created_at"))
                if skill.get("first_release_created_at") is not None
                else None
            ),
        }
        if args.json:
            print(json.dumps(payload, indent=2, sort_keys=True))
            return 0

        release_download_stats = payload["release_download_stats"]
        skill_download_stats = payload["download_stats"]
        first_release_created_at = payload["first_release_created_at"] or "N/A"
        release_version = release.get("version")
        release_version_s = str(release_version) if release_version is not None else str(args.version)
        print(f"skill: {ref.key}")
        print(f"version: {release_version_s}")
        author_id, author_name, author_picture = _extract_author_summary(skill)
        if author_id:
            print(f"author_user_id: {author_id}")
        if author_name:
            print(f"author_display_name: {author_name}")
        if author_picture:
            print(f"author_google_picture: {author_picture}")
        homepage_url = skill.get("homepage_url")
        if isinstance(homepage_url, str) and homepage_url.strip():
            print(f"homepage_url: {homepage_url.strip()}")
        print(f"created_at: {first_release_created_at}")
        print("downloads:")
        print(f"  total: {skill_download_stats['total']}")
        print(f"  last_week: {skill_download_stats['last_week']}")
        print(f"  last_month: {skill_download_stats['last_month']}")
        print(f"downloads_this_release: {release_download_stats['total']}")
        print(f"description_source: {description_source}")
        if description_md:
            print("description_md:")
            print(description_md)
        return 0

    if args.subcmd == "releases":
        cfg_file = load_config()
        cfg = _merge_cfg(cfg_file, args)
        base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
        if not base_url:
            raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")

        if args.page < 1:
            raise SkilldockError("--page must be >= 1.")
        if args.per_page < 1 or args.per_page > 100:
            raise SkilldockError("--per-page must be between 1 and 100.")

        ref = parse_skill_ref(args.skill)
        release_path = f"/v1/skills/{quote(ref.namespace, safe='')}/{quote(ref.slug, safe='')}/releases"
        client = SkilldockClient(openapi_url=cfg.openapi_url, base_url=base_url, token=cfg.token, timeout_s=cfg.timeout_s)
        try:
            resp = client.request(
                method="GET",
                path=release_path,
                params={"page": args.page, "per_page": args.per_page},
                auth=True,
            )
            data = _unwrap_success_envelope(resp.json())
        finally:
            client.close()

        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0

        items = data.get("items") if isinstance(data, dict) else None
        page = data.get("page") if isinstance(data, dict) else None
        per_page = data.get("per_page") if isinstance(data, dict) else None
        has_more = bool(data.get("has_more")) if isinstance(data, dict) else False
        print(f"skill: {ref.key}")
        print(f"page: {page if isinstance(page, int) else args.page}")
        print(f"per_page: {per_page if isinstance(per_page, int) else args.per_page}")
        print(f"has_more: {'true' if has_more else 'false'}")

        if not isinstance(items, list):
            return 0

        rows: list[list[str]] = [["VERSION", "CREATED_AT"]]
        for item in items:
            if not isinstance(item, dict):
                continue
            version = str(item.get("version", ""))
            created_at = str(item.get("created_at", ""))
            rows.append([version, created_at])
        _print_table(rows)
        return 0

    if args.subcmd == "set-ton-wallet":
        cfg_file = load_config()
        cfg = _merge_cfg(cfg_file, args)
        base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
        if not base_url:
            raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")
        if not cfg.token:
            raise SkilldockError("Missing token. Run `skilldock auth login` first.")
        _require_fresh_token(cfg.token)

        client = SkilldockClient(openapi_url=cfg.openapi_url, base_url=base_url, token=cfg.token, timeout_s=cfg.timeout_s)
        try:
            resp = client.request(
                method="POST",
                path="/v1/me/payout-methods/ton",
                json_body={"ton_wallet_address": args.ton_wallet_address},
                auth=True,
            )
            data = _unwrap_success_envelope(resp.json())
        finally:
            client.close()

        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0
        method = data.get("method") if isinstance(data, dict) and isinstance(data.get("method"), dict) else {}
        print(f"id: {str(method.get('id', ''))}")
        print(f"kind: {str(method.get('kind', ''))}")
        print(f"ton_wallet_address: {str(method.get('ton_wallet_address', ''))}")
        print(f"status: {str(method.get('status', ''))}")
        return 0

    if args.subcmd == "set-price":
        cfg_file = load_config()
        cfg = _merge_cfg(cfg_file, args)
        base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
        if not base_url:
            raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")
        if not cfg.token:
            raise SkilldockError("Missing token. Run `skilldock auth login` first.")
        _require_fresh_token(cfg.token)
        ref = parse_skill_ref(args.skill)

        client = SkilldockClient(openapi_url=cfg.openapi_url, base_url=base_url, token=cfg.token, timeout_s=cfg.timeout_s)
        try:
            resp = client.request(
                method="POST",
                path=f"/v1/skills/{quote(ref.namespace, safe='')}/{quote(ref.slug, safe='')}/prices",
                json_body={"price_usd": args.price_usd},
                auth=True,
            )
            data = _unwrap_success_envelope(resp.json())
        finally:
            client.close()

        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0
        price = data.get("price") if isinstance(data, dict) and isinstance(data.get("price"), dict) else {}
        print(f"skill: {ref.key}")
        print(f"price_id: {str(price.get('id', ''))}")
        print(f"price_usd: {str(price.get('price_usd', ''))}")
        print(f"created_at: {str(price.get('created_at', ''))}")
        return 0

    if args.subcmd == "set-commerce":
        cfg_file = load_config()
        cfg = _merge_cfg(cfg_file, args)
        base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
        if not base_url:
            raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")
        if not cfg.token:
            raise SkilldockError("Missing token. Run `skilldock auth login` first.")
        _require_fresh_token(cfg.token)
        ref = parse_skill_ref(args.skill)

        body: dict[str, Any] = {"is_for_sale": args.is_for_sale == "true"}
        if args.visibility:
            body["visibility"] = args.visibility
        if args.selling_description_md is not None:
            body["selling_description_md"] = args.selling_description_md

        client = SkilldockClient(openapi_url=cfg.openapi_url, base_url=base_url, token=cfg.token, timeout_s=cfg.timeout_s)
        try:
            resp = client.request(
                method="PATCH",
                path=f"/v1/skills/{quote(ref.namespace, safe='')}/{quote(ref.slug, safe='')}/commerce",
                json_body=body,
                auth=True,
            )
            data = _unwrap_success_envelope(resp.json())
        finally:
            client.close()

        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0
        sale_obj = data.get("sale") if isinstance(data, dict) and isinstance(data.get("sale"), dict) else {}
        owner_setup = sale_obj.get("owner_setup") if isinstance(sale_obj.get("owner_setup"), dict) else {}
        skill_obj = data.get("skill") if isinstance(data, dict) and isinstance(data.get("skill"), dict) else {}
        print(f"skill: {str(skill_obj.get('namespace', ''))}/{str(skill_obj.get('slug', ''))}".strip("/"))
        print(f"visibility: {str(skill_obj.get('visibility', ''))}")
        print(f"is_for_sale: {'true' if bool(sale_obj.get('is_for_sale')) else 'false'}")
        print(f"active_price_usd: {str(sale_obj.get('active_price_usd', ''))}")
        print(f"sold_total: {str(sale_obj.get('sold_total', ''))}")
        print(f"owner_setup_status: {str(owner_setup.get('status', ''))}")
        missing = owner_setup.get("missing_requirements")
        if isinstance(missing, list):
            print(f"owner_setup_missing_requirements: {','.join(str(x) for x in missing)}")
        return 0

    if args.subcmd == "buy":
        cfg_file = load_config()
        cfg = _merge_cfg(cfg_file, args)
        base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
        if not base_url:
            raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")
        if not cfg.token:
            raise SkilldockError("Missing token. Run `skilldock auth login` first.")
        _require_fresh_token(cfg.token)
        ref = parse_skill_ref(args.skill)

        client = SkilldockClient(openapi_url=cfg.openapi_url, base_url=base_url, token=cfg.token, timeout_s=cfg.timeout_s)
        try:
            resp = client.request(
                method="POST",
                path=f"/v1/skills/{quote(ref.namespace, safe='')}/{quote(ref.slug, safe='')}/buy",
                auth=True,
            )
            data = _unwrap_success_envelope(resp.json())
            invoice = data.get("invoice") if isinstance(data, dict) and isinstance(data.get("invoice"), dict) else {}
            if args.poll and invoice:
                interval_s = max(0.2, float(args.poll_interval_s))
                deadline = time.time() + max(1.0, float(args.poll_timeout_s))
                invoice_id = str(invoice.get("id", "")).strip()
                while invoice_id:
                    if time.time() > deadline:
                        break
                    status = str(invoice.get("status", "")).strip()
                    if status in ("paid", "expired"):
                        break
                    time.sleep(interval_s)
                    st_resp = client.request(
                        method="GET",
                        path=f"/v1/skill-purchases/invoices/{quote(invoice_id, safe='')}",
                        auth=True,
                    )
                    st_data = _unwrap_success_envelope(st_resp.json())
                    invoice = st_data.get("invoice") if isinstance(st_data, dict) and isinstance(st_data.get("invoice"), dict) else invoice
                data = {"created": data.get("created"), "invoice": invoice}
        finally:
            client.close()

        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0
        invoice = data.get("invoice") if isinstance(data, dict) and isinstance(data.get("invoice"), dict) else {}
        print(f"created: {'true' if bool(data.get('created')) else 'false'}")
        print(f"invoice_id: {str(invoice.get('id', ''))}")
        print(f"status: {str(invoice.get('status', ''))}")
        print(f"pay_to_address: {str(invoice.get('pay_to_address', ''))}")
        print(f"memo: {str(invoice.get('memo', ''))}")
        print(f"amount_ton: {str(invoice.get('amount_ton', ''))}")
        print(f"expires_at: {str(invoice.get('expires_at', ''))}")
        print(f"access_granted: {'true' if bool(invoice.get('access_granted')) else 'false'}")
        return 0

    if args.subcmd == "invoice":
        cfg_file = load_config()
        cfg = _merge_cfg(cfg_file, args)
        base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
        if not base_url:
            raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")
        if not cfg.token:
            raise SkilldockError("Missing token. Run `skilldock auth login` first.")
        _require_fresh_token(cfg.token)

        client = SkilldockClient(openapi_url=cfg.openapi_url, base_url=base_url, token=cfg.token, timeout_s=cfg.timeout_s)
        try:
            resp = client.request(
                method="GET",
                path=f"/v1/skill-purchases/invoices/{quote(args.invoice_id, safe='')}",
                auth=True,
            )
            data = _unwrap_success_envelope(resp.json())
        finally:
            client.close()

        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0
        invoice = data.get("invoice") if isinstance(data, dict) and isinstance(data.get("invoice"), dict) else {}
        print(f"invoice_id: {str(invoice.get('id', ''))}")
        print(f"status: {str(invoice.get('status', ''))}")
        print(f"paid_at: {str(invoice.get('paid_at', ''))}")
        print(f"tx_hash: {str(invoice.get('tx_hash', ''))}")
        print(f"access_granted: {'true' if bool(invoice.get('access_granted')) else 'false'}")
        return 0

    if args.subcmd == "sales":
        cfg_file = load_config()
        cfg = _merge_cfg(cfg_file, args)
        base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
        if not base_url:
            raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")
        if not cfg.token:
            raise SkilldockError("Missing token. Run `skilldock auth login` first.")
        _require_fresh_token(cfg.token)
        if args.page < 1:
            raise SkilldockError("--page must be >= 1.")
        if args.per_page < 1:
            raise SkilldockError("--per-page must be >= 1.")

        path = "/v1/me/sales"
        if args.skill:
            ref = parse_skill_ref(args.skill)
            path = f"/v1/skills/{quote(ref.namespace, safe='')}/{quote(ref.slug, safe='')}/sales"

        client = SkilldockClient(openapi_url=cfg.openapi_url, base_url=base_url, token=cfg.token, timeout_s=cfg.timeout_s)
        try:
            resp = client.request(
                method="GET",
                path=path,
                params={"page": args.page, "per_page": args.per_page},
                auth=True,
            )
            data = _unwrap_success_envelope(resp.json())
        finally:
            client.close()

        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0

        page = data.get("page") if isinstance(data, dict) else None
        per_page = data.get("per_page") if isinstance(data, dict) else None
        has_more = bool(data.get("has_more")) if isinstance(data, dict) else False
        total_sales = data.get("total_sales") if isinstance(data, dict) else None
        print(f"page: {page if isinstance(page, int) else args.page}")
        print(f"per_page: {per_page if isinstance(per_page, int) else args.per_page}")
        print(f"has_more: {'true' if has_more else 'false'}")
        if isinstance(total_sales, int):
            print(f"total_sales: {total_sales}")
        items = data.get("items") if isinstance(data, dict) and isinstance(data.get("items"), list) else []
        rows: list[list[str]] = [["SALE_ID", "PAID_AT", "AMOUNT_USD", "AMOUNT_TON", "BUYER", "SKILL", "TX_HASH"]]
        for it in items:
            if not isinstance(it, dict):
                continue
            buyer = it.get("buyer") if isinstance(it.get("buyer"), dict) else {}
            buyer_name = str(buyer.get("display_name", "")).strip() or str(it.get("buyer_display_name", "")).strip()
            buyer_id = str(buyer.get("user_id", "")).strip() or str(it.get("buyer_user_id", "")).strip()
            buyer_s = buyer_name or buyer_id
            skill_obj = it.get("skill") if isinstance(it.get("skill"), dict) else {}
            skill_s = (
                f"{str(skill_obj.get('namespace', '')).strip()}/{str(skill_obj.get('slug', '')).strip()}".strip("/")
                if skill_obj
                else (args.skill or "")
            )
            rows.append(
                [
                    str(it.get("sale_id", "")),
                    str(it.get("paid_at", "")),
                    str(it.get("amount_usd", "")),
                    str(it.get("amount_ton", "")),
                    buyer_s,
                    skill_s,
                    str(it.get("tx_hash", "")),
                ]
            )
        _print_table(rows)
        return 0

    raise AssertionError("unreachable")


def cmd_skill(args: argparse.Namespace) -> int:
    if args.subcmd == "verify":
        try:
            pkg = package_skill(Path(args.path))
        except SkillPackageError as e:
            raise SkilldockError(str(e)) from e

        out = {
            "ok": True,
            "root": str(pkg.root),
            "file_count": pkg.file_count,
            "size_bytes": pkg.size_bytes,
            "sha256": pkg.sha256,
            "warnings": pkg.warnings,
        }
        if args.json:
            print(json.dumps(out, indent=2, sort_keys=True))
            return 0
        print(f"ok: true")
        print(f"root: {pkg.root}")
        print(f"files: {pkg.file_count}")
        print(f"zip_size_bytes: {pkg.size_bytes}")
        print(f"sha256: {pkg.sha256}")
        for w in pkg.warnings:
            print(f"warning: {w}", file=sys.stderr)
        return 0

    if args.subcmd == "upload":
        homepage_url = _normalize_homepage_url(getattr(args, "homepage_url", None))
        try:
            pkg = package_skill(Path(args.path), top_level_dir=args.slug)
        except SkillPackageError as e:
            raise SkilldockError(str(e)) from e

        dependencies_payload: Any | None = None
        if args.dependencies_json and args.dependency:
            raise SkilldockError("Use either --dependencies-json or --dependency (repeatable), not both.")
        if args.dependencies_json:
            dependencies_payload = _load_json_arg(args.dependencies_json)
            if not isinstance(dependencies_payload, (list, dict)):
                raise SkilldockError("--dependencies-json must decode to a JSON array or object.")
        elif args.dependency:
            dependencies_payload = list(args.dependency)

        if args.dry_run:
            print(
                json.dumps(
                    {
                        "dry_run": True,
                        "root": str(pkg.root),
                        "file_count": pkg.file_count,
                        "size_bytes": pkg.size_bytes,
                        "sha256": pkg.sha256,
                        "warnings": pkg.warnings,
                        "namespace": args.namespace,
                        "slug": args.slug,
                        "version": args.version,
                        "visibility": args.visibility or "public",
                        "homepage_url": homepage_url,
                        "dependencies": dependencies_payload,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        cfg_file = load_config()
        cfg = _merge_cfg(cfg_file, args)
        base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
        if not base_url:
            raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")
        if not cfg.token:
            raise SkilldockError("Missing token. Run `skilldock auth login` first.")
        _require_fresh_token(cfg.token)

        client = SkilldockClient(openapi_url=cfg.openapi_url, base_url=base_url, token=cfg.token, timeout_s=cfg.timeout_s)
        try:
            params: dict[str, Any] = {}
            if args.version:
                params["version"] = args.version
            if args.visibility:
                params["visibility"] = args.visibility
            if homepage_url:
                params["homepage_url"] = homepage_url

            def _upload_release() -> Any:
                form_fields: dict[str, Any] = {}
                if dependencies_payload is not None:
                    form_fields["dependencies"] = json.dumps(dependencies_payload, separators=(",", ":"))
                # Backend expects multipart field "file" for the zip.
                files = {
                    "file": (
                        f"{args.slug}.zip",
                        pkg.zip_bytes,
                        "application/zip",
                    )
                }
                response = client.request(
                    method="POST",
                    path=f"/v1/skills/{args.namespace}/{args.slug}/releases",
                    params=params or None,
                    data=form_fields or None,
                    files=files,
                    headers={"x-skilldock-sha256": pkg.sha256},
                    auth=True,
                )
                return _unwrap_success_envelope(response.json())

            try:
                data = _upload_release()
            except SkilldockHTTPError as e:
                if e.status_code == 409:
                    detail = _http_error_detail(e.body) or "Release version already exists."
                    target = f"{args.namespace}/{args.slug}@{args.version}" if args.version else f"{args.namespace}/{args.slug}"
                    raise SkilldockError(
                        f"Release version conflict for {target}. "
                        "Release versions are immutable; publish a new version (for example, 0.1.0 -> 0.1.1). "
                        f"Server detail: {detail}"
                    ) from e
                if e.status_code == 404 and args.create_namespace and "Namespace not found" in e.body:
                    # Create namespace then retry once.
                    resp2 = client.request(
                        method="POST",
                        path="/v1/namespaces",
                        json_body={"slug": args.namespace, "kind": "org"},
                        auth=True,
                    )
                    _unwrap_success_envelope(resp2.json())
                    data = _upload_release()
                else:
                    raise
        finally:
            client.close()

        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0

        release = data.get("release") if isinstance(data, dict) else None
        if not isinstance(release, dict):
            release = data if isinstance(data, dict) else {}

        version = str(release.get("version", "")) if isinstance(release, dict) else ""
        print(f"Release uploaded: {args.namespace}/{args.slug}@{version or args.version or ''}".rstrip("@"))

        files = release.get("files") if isinstance(release, dict) else None
        if isinstance(files, list) and files:
            rows: list[list[str]] = [["KIND", "SIZE", "SHA256", "DOWNLOAD_URL"]]
            for f in files:
                if not isinstance(f, dict):
                    continue
                rows.append(
                    [
                        str(f.get("kind", "")),
                        str(f.get("size_bytes", "")),
                        str(f.get("sha256", "")),
                        str(f.get("download_url", "")),
                    ]
                )
            _print_table(rows)

        dependencies = release.get("dependencies") if isinstance(release, dict) else None
        if isinstance(dependencies, list) and dependencies:
            rows = [["SKILL", "VERSION_REQUIREMENT", "RELEASE_VERSION"]]
            for d in dependencies:
                if not isinstance(d, dict):
                    continue
                dep_ns = str(d.get("namespace", "")).strip()
                dep_slug = str(d.get("slug", "")).strip()
                dep_skill = "/".join(x for x in (dep_ns, dep_slug) if x)
                rows.append(
                    [
                        dep_skill,
                        str(d.get("version_requirement", "")),
                        str(d.get("release_version", "")),
                    ]
                )
            _print_table(rows)

        print("Upload complete.")
        return 0

    raise AssertionError("unreachable")


def cmd_namespaces(args: argparse.Namespace) -> int:
    if args.subcmd == "list":
        cfg_file = load_config()
        cfg = _merge_cfg(cfg_file, args)
        base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
        if not base_url:
            raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")
        if not cfg.token:
            raise SkilldockError("Missing token. Run `skilldock auth login` first.")
        _require_fresh_token(cfg.token)

        client = SkilldockClient(openapi_url=cfg.openapi_url, base_url=base_url, token=cfg.token, timeout_s=cfg.timeout_s)
        try:
            params: dict[str, Any] = {}
            if args.page:
                params["page"] = args.page
            if args.per_page:
                params["per_page"] = args.per_page
            resp = client.request(method="GET", path="/v1/me/namespaces", params=params or None, auth=True)
            data = _unwrap_success_envelope(resp.json())
        finally:
            client.close()

        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0

        items = data.get("items") if isinstance(data, dict) else None
        if not isinstance(items, list):
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0

        rows: list[list[str]] = [["SLUG", "KIND", "ROLE", "VERIFIED_AT"]]
        for it in items:
            if not isinstance(it, dict):
                continue
            rows.append(
                [
                    str(it.get("slug", "")),
                    str(it.get("kind", "")),
                    str(it.get("role", "")),
                    str(it.get("verified_at", "")),
                ]
            )
        _print_table(rows)
        return 0

    if args.subcmd == "create":
        cfg_file = load_config()
        cfg = _merge_cfg(cfg_file, args)
        base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
        if not base_url:
            raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")
        if not cfg.token:
            raise SkilldockError("Missing token. Run `skilldock auth login` first.")
        _require_fresh_token(cfg.token)

        client = SkilldockClient(openapi_url=cfg.openapi_url, base_url=base_url, token=cfg.token, timeout_s=cfg.timeout_s)
        try:
            resp = client.request(method="POST", path="/v1/namespaces", json_body={"slug": args.slug, "kind": "org"}, auth=True)
            data = _unwrap_success_envelope(resp.json())
        finally:
            client.close()

        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0
        print(json.dumps(data, indent=2, sort_keys=True))
        return 0

    raise AssertionError("unreachable")


def cmd_users(args: argparse.Namespace) -> int:
    if args.subcmd == "get":
        cfg_file = load_config()
        cfg = _merge_cfg(cfg_file, args)
        base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
        if not base_url:
            raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")
        if args.page < 1:
            raise SkilldockError("--page must be >= 1.")
        if args.per_page < 1:
            raise SkilldockError("--per-page must be >= 1.")

        user_id = quote(str(args.user_id), safe="")
        client = SkilldockClient(openapi_url=cfg.openapi_url, base_url=base_url, token=cfg.token, timeout_s=cfg.timeout_s)
        try:
            resp = client.request(
                method="GET",
                path=f"/v1/user/{user_id}",
                params={"page": args.page, "per_page": args.per_page},
                auth=True,
            )
            data = _unwrap_success_envelope(resp.json())
        finally:
            client.close()

        if args.json:
            print(json.dumps(data, indent=2, sort_keys=True))
            return 0

        user = data.get("user") if isinstance(data, dict) and isinstance(data.get("user"), dict) else {}
        skills = data.get("skills") if isinstance(data, dict) and isinstance(data.get("skills"), dict) else {}
        items = skills.get("items") if isinstance(skills.get("items"), list) else []
        user_name = str(user.get("display_name", "")).strip()
        user_picture = str(user.get("google_picture", "")).strip()

        print(f"user_id: {str(user.get('id', args.user_id))}")
        if user_name:
            print(f"display_name: {user_name}")
        if user_picture:
            print(f"google_picture: {user_picture}")

        page = skills.get("page")
        per_page = skills.get("per_page")
        has_more = bool(skills.get("has_more"))
        print(f"skills_page: {page if isinstance(page, int) else args.page}")
        print(f"skills_per_page: {per_page if isinstance(per_page, int) else args.per_page}")
        print(f"skills_has_more: {'true' if has_more else 'false'}")

        rows: list[list[str]] = [["SKILL", "TITLE", "UPDATED_AT", "PRICE_USD", "SOLD", "CAN_BUY"]]
        for item in items:
            if not isinstance(item, dict):
                continue
            ns = str(item.get("namespace", "")).strip()
            slug = str(item.get("slug", "")).strip()
            sale = _extract_sale_summary(item.get("sale"))
            rows.append(
                [
                    f"{ns}/{slug}".strip("/"),
                    str(item.get("title", "")),
                    str(item.get("updated_at", "")),
                    str(sale["price_usd"]),
                    str(sale["sold_total"]),
                    "true" if bool(sale["can_buy"]) else "false",
                ]
            )
        _print_table(rows)
        return 0

    raise AssertionError("unreachable")


def _make_runtime_client(args: argparse.Namespace) -> SkilldockClient:
    cfg_file = load_config()
    cfg = _merge_cfg(cfg_file, args)
    base_url = (cfg.base_url or _origin_from_url(cfg.openapi_url) or "").rstrip("/")
    if not base_url:
        raise SkilldockError("Missing base_url. Set it via --base-url or SKILLDOCK_BASE_URL or config.")
    return SkilldockClient(openapi_url=cfg.openapi_url, base_url=base_url, token=cfg.token, timeout_s=cfg.timeout_s)


def _split_install_skill_and_requirement(skill_arg: str, version_arg: str | None) -> tuple[str, str | None]:
    skill = skill_arg.strip()
    if not skill:
        raise SkilldockError("Invalid skill identifier ''. Expected <namespace>/<slug>.")

    at_idx = skill.rfind("@")
    if at_idx > 0:
        shorthand_skill = skill[:at_idx].strip()
        shorthand_req = skill[at_idx + 1 :].strip()
        if "/" in shorthand_skill and shorthand_req:
            if version_arg:
                raise SkilldockError("Specify version either as @<version> or --version, not both.")
            return shorthand_skill, shorthand_req
    return skill, version_arg


def cmd_install(args: argparse.Namespace) -> int:
    skills_dir = Path(args.skills_dir).expanduser()
    skill, requirement = _split_install_skill_and_requirement(args.skill, args.version)
    client = _make_runtime_client(args)
    try:
        repo = ApiReleaseRepository(client)
        manager = LocalSkillManager(skills_dir=skills_dir, repo=repo)
        result = manager.install(skill=skill, requirement=requirement)
    finally:
        client.close()

    payload = {
        "installed": list(result.installed),
        "updated": list(result.updated),
        "removed": list(result.removed),
        "unchanged": list(result.unchanged),
        "warnings": list(result.warnings),
        "manifest_path": str(result.manifest_path),
        "lock_path": str(result.lock_path),
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(f"skills_dir: {skills_dir.resolve()}")
    print(f"manifest: {result.manifest_path}")
    print(f"lock: {result.lock_path}")
    _print_table(
        [
            ["ACTION", "COUNT"],
            ["installed", str(len(result.installed))],
            ["updated", str(len(result.updated))],
            ["removed", str(len(result.removed))],
            ["unchanged", str(len(result.unchanged))],
        ]
    )
    for key in result.installed:
        print(f"installed: {key}")
    for key in result.updated:
        print(f"updated: {key}")
    for key in result.removed:
        print(f"removed: {key}")
    for key in result.unchanged:
        print(f"unchanged: {key}")
    for warning in result.warnings:
        print(f"warning: {warning}")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    skills_dir = Path(args.skills_dir).expanduser()
    client = _make_runtime_client(args)
    try:
        repo = ApiReleaseRepository(client)
        manager = LocalSkillManager(skills_dir=skills_dir, repo=repo)
        result = manager.uninstall(skill=args.skill)
    finally:
        client.close()

    payload = {
        "installed": list(result.installed),
        "updated": list(result.updated),
        "removed": list(result.removed),
        "unchanged": list(result.unchanged),
        "manifest_path": str(result.manifest_path),
        "lock_path": str(result.lock_path),
    }

    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0

    print(f"skills_dir: {skills_dir.resolve()}")
    print(f"manifest: {result.manifest_path}")
    print(f"lock: {result.lock_path}")
    _print_table(
        [
            ["ACTION", "COUNT"],
            ["installed", str(len(result.installed))],
            ["updated", str(len(result.updated))],
            ["removed", str(len(result.removed))],
            ["unchanged", str(len(result.unchanged))],
        ]
    )
    for key in result.removed:
        print(f"removed: {key}")
    for key in result.unchanged:
        print(f"unchanged: {key}")
    return 0


def _print_response(resp, *, raw: bool) -> None:
    if raw:
        sys.stdout.write(resp.text)
        if not resp.text.endswith("\n"):
            sys.stdout.write("\n")
        return
    ctype = resp.headers.get("content-type", "")
    if "application/json" in ctype:
        print(json.dumps(resp.json(), indent=2, sort_keys=True))
        return
    try:
        obj = resp.json()
        print(json.dumps(obj, indent=2, sort_keys=True))
    except Exception:
        print(resp.text)


def _http_error_detail(body: str) -> str | None:
    text = body.strip()
    if not text:
        return None
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return text
    if isinstance(obj, dict):
        for key in ("message", "detail", "error"):
            value = obj.get(key)
            if isinstance(value, str):
                value = value.strip()
                if value:
                    return value
    return text


def _format_http_error(err: SkilldockHTTPError) -> str:
    detail = _http_error_detail(err.body)
    if err.status_code == 401:
        base = "HTTP 401 Unauthorized. Missing or invalid auth token."
    elif err.status_code == 403:
        base = "HTTP 403 Forbidden. You are authenticated but not allowed to access this resource."
    elif err.status_code == 404:
        base = "HTTP 404 Not Found. Resource does not exist or is not visible to your account."
    else:
        base = f"HTTP {err.status_code}"
    if detail:
        return f"{base} {detail}"
    return base


def cmd_call(args: argparse.Namespace) -> int:
    cfg_file = load_config()
    cfg = _merge_cfg(cfg_file, args)
    if not args.no_auth and cfg.token:
        _require_fresh_token(cfg.token)
    client = _client_from_cfg(cfg)
    try:
        params = dict(_parse_kv(x) for x in args.param)
        data = dict(_parse_kv(x) for x in args.data)
        files = _load_files(args.file) if args.file else None
        headers = _load_headers(args.header) if args.header else None
        json_body = _load_json_arg(args.json_body) if args.json_body else None
        resp = client.request_operation(
            args.operation_id,
            params=params or None,
            json_body=json_body,
            data=data or None,
            files=files,
            headers=headers,
            auth=not args.no_auth,
        )
        _print_response(resp, raw=args.raw)
        return 0
    finally:
        client.close()


def cmd_request(args: argparse.Namespace) -> int:
    cfg_file = load_config()
    cfg = _merge_cfg(cfg_file, args)
    if not args.no_auth and cfg.token:
        _require_fresh_token(cfg.token)
    client = _client_from_cfg(cfg)
    try:
        query = dict(_parse_kv(x) for x in args.query)
        data = dict(_parse_kv(x) for x in args.data)
        files = _load_files(args.file) if args.file else None
        headers = _load_headers(args.header) if args.header else None
        json_body = _load_json_arg(args.json_body) if args.json_body else None
        resp = client.request(
            method=args.method,
            path=args.path,
            params=query or None,
            json_body=json_body,
            data=data or None,
            files=files,
            headers=headers,
            auth=not args.no_auth,
        )
        _print_response(resp, raw=args.raw)
        return 0
    finally:
        client.close()


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.cmd == "config":
            return cmd_config(args)
        if args.cmd == "auth":
            return cmd_auth(args)
        if args.cmd == "tokens":
            return cmd_tokens(args)
        if args.cmd == "ops":
            return cmd_ops(args)
        if args.cmd == "skills":
            return cmd_skills(args)
        if args.cmd == "skill":
            return cmd_skill(args)
        if args.cmd in ("install", "i"):
            return cmd_install(args)
        if args.cmd in ("uninstall", "remove", "rm"):
            return cmd_uninstall(args)
        if args.cmd == "namespaces":
            return cmd_namespaces(args)
        if args.cmd == "users":
            return cmd_users(args)
        if args.cmd == "call":
            return cmd_call(args)
        if args.cmd == "request":
            return cmd_request(args)
        raise AssertionError("unreachable")
    except SkilldockHTTPError as e:
        print(f"error: {_format_http_error(e)}", file=sys.stderr)
        return 1
    except (OperationNotFoundError, AuthRequiredError, SkilldockError) as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
