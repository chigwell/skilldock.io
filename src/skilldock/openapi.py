from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urlsplit, urlunsplit

import httpx

HTTP_METHODS = {"get", "post", "put", "patch", "delete", "head", "options", "trace"}


def _sanitize_identifier(s: str) -> str:
    s = s.strip()
    s = re.sub(r"[^0-9A-Za-z_]+", "_", s)
    s = re.sub(r"_{2,}", "_", s).strip("_")
    if not s:
        return "op"
    if s[0].isdigit():
        return "op_" + s
    return s


def _extract_origin(url: str) -> str:
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def _substitute_server_variables(server_url: str, variables: dict[str, Any] | None) -> str:
    if not variables:
        return server_url
    for name, var in variables.items():
        default = None
        if isinstance(var, dict):
            default = var.get("default")
        if default is None:
            continue
        server_url = server_url.replace("{" + name + "}", str(default))
    return server_url


def derive_base_url(openapi_url: str, raw: dict[str, Any]) -> str:
    origin = _extract_origin(openapi_url)
    servers = raw.get("servers") or []
    if isinstance(servers, list) and servers:
        first = servers[0]
        if isinstance(first, dict) and isinstance(first.get("url"), str):
            server_url = _substitute_server_variables(first["url"], first.get("variables"))
            if server_url.startswith("/"):
                return (origin + server_url).rstrip("/")
            if "://" in server_url:
                return server_url.rstrip("/")
    return origin.rstrip("/")


def load_openapi(openapi_url: str, *, timeout_s: float = 30.0) -> dict[str, Any]:
    # Local file support for offline usage.
    if openapi_url.startswith("file://"):
        path = Path(openapi_url.removeprefix("file://"))
        return json.loads(path.read_text(encoding="utf-8"))
    if "://" not in openapi_url:
        path = Path(openapi_url)
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))

    with httpx.Client(timeout=timeout_s, follow_redirects=True) as client:
        resp = client.get(openapi_url, headers={"accept": "application/json"})
        resp.raise_for_status()
        return resp.json()


@dataclass(frozen=True)
class AuthStrategy:
    kind: str  # "http-bearer" | "apiKey-header" | "unknown"
    header: str
    scheme: str | None = None  # e.g. "Bearer"


def detect_auth_strategy(raw: dict[str, Any]) -> AuthStrategy:
    schemes = (raw.get("components") or {}).get("securitySchemes") or {}
    if not isinstance(schemes, dict):
        schemes = {}

    # Prefer bearer.
    for _, s in schemes.items():
        if not isinstance(s, dict):
            continue
        if s.get("type") == "http" and str(s.get("scheme")).lower() == "bearer":
            return AuthStrategy(kind="http-bearer", header="Authorization", scheme="Bearer")

    # Then header apiKey.
    for _, s in schemes.items():
        if not isinstance(s, dict):
            continue
        if s.get("type") == "apiKey" and s.get("in") == "header" and isinstance(s.get("name"), str):
            return AuthStrategy(kind="apiKey-header", header=s["name"], scheme=None)

    return AuthStrategy(kind="unknown", header="Authorization", scheme="Bearer")


@dataclass(frozen=True)
class OpenAPIOperation:
    operation_id: str
    python_name: str
    method: str
    path: str
    summary: str | None
    description: str | None
    parameters: list[dict[str, Any]]
    request_body: dict[str, Any] | None
    requires_auth: bool
    deprecated: bool


@dataclass(frozen=True)
class OpenAPISpec:
    openapi_url: str
    base_url: str
    auth: AuthStrategy
    operations: dict[str, OpenAPIOperation]

    def get(self, operation_id: str) -> OpenAPIOperation:
        return self.operations[operation_id]


def iter_operations(raw: dict[str, Any]) -> Iterable[tuple[str, str, dict[str, Any], dict[str, Any]]]:
    """
    Yields (path, method, path_item, operation) tuples.
    """
    paths = raw.get("paths") or {}
    if not isinstance(paths, dict):
        return
    for path, path_item in paths.items():
        if not isinstance(path, str) or not isinstance(path_item, dict):
            continue
        for method, op in path_item.items():
            if str(method).lower() not in HTTP_METHODS:
                continue
            if not isinstance(op, dict):
                continue
            yield path, str(method).lower(), path_item, op


def parse_spec(openapi_url: str, raw: dict[str, Any]) -> OpenAPISpec:
    base_url = derive_base_url(openapi_url, raw)
    auth = detect_auth_strategy(raw)

    global_security = raw.get("security")
    ops: dict[str, OpenAPIOperation] = {}
    used_ids: set[str] = set()
    used_py: set[str] = set()

    for path, method, path_item, op in iter_operations(raw):
        op_id = op.get("operationId")
        if not isinstance(op_id, str) or not op_id.strip():
            op_id = f"{method}_{path}"
        op_id = op_id.strip()

        # Ensure uniqueness in case the spec has duplicate/empty operationId values.
        base_id = op_id
        i = 2
        while op_id in used_ids:
            op_id = f"{base_id}_{i}"
            i += 1
        used_ids.add(op_id)

        python_name = _sanitize_identifier(op_id).lower()
        base_py = python_name
        j = 2
        while python_name in used_py:
            python_name = f"{base_py}_{j}"
            j += 1
        used_py.add(python_name)
        summary = op.get("summary") if isinstance(op.get("summary"), str) else None
        description = op.get("description") if isinstance(op.get("description"), str) else None
        deprecated = bool(op.get("deprecated", False))

        path_params = path_item.get("parameters") if isinstance(path_item.get("parameters"), list) else []
        op_params = op.get("parameters") if isinstance(op.get("parameters"), list) else []
        parameters = [p for p in (path_params + op_params) if isinstance(p, dict)]

        request_body = op.get("requestBody") if isinstance(op.get("requestBody"), dict) else None

        if "security" in op:
            security = op.get("security")
        else:
            security = global_security
        requires_auth = bool(security)

        ops[op_id] = OpenAPIOperation(
            operation_id=op_id,
            python_name=python_name,
            method=method,
            path=path,
            summary=summary,
            description=description,
            parameters=parameters,
            request_body=request_body,
            requires_auth=requires_auth,
            deprecated=deprecated,
        )

    return OpenAPISpec(openapi_url=openapi_url, base_url=base_url, auth=auth, operations=ops)


def guess_google_auth_url_operation(spec: OpenAPISpec) -> OpenAPIOperation | None:
    """
    Best-effort heuristic: tries to find an operation that returns a Google auth URL.
    Works even when we don't know exact endpoint names.
    """
    best: tuple[int, OpenAPIOperation] | None = None
    for op in spec.operations.values():
        hay = " ".join(
            [
                op.operation_id.lower(),
                op.python_name.lower(),
                op.method.lower(),
                op.path.lower(),
                (op.summary or "").lower(),
                (op.description or "").lower(),
            ]
        )
        score = 0
        if op.method == "get":
            score += 2
        if "google" in hay:
            score += 5
        if "auth" in hay or "login" in hay or "oauth" in hay:
            score += 3
        if "url" in hay or "authorize" in hay:
            score += 2
        if score <= 0:
            continue
        if best is None or score > best[0]:
            best = (score, op)
    return best[1] if best else None


def extract_first_url(value: Any) -> str | None:
    if isinstance(value, str):
        if value.startswith("http://") or value.startswith("https://"):
            return value
        return None
    if isinstance(value, list):
        for v in value:
            u = extract_first_url(v)
            if u:
                return u
        return None
    if isinstance(value, dict):
        # Prefer common keys.
        for k in ("url", "authUrl", "auth_url", "authorizationUrl", "authorization_url", "loginUrl", "login_url"):
            if k in value:
                u = extract_first_url(value[k])
                if u:
                    return u
        # Otherwise scan everything.
        for v in value.values():
            u = extract_first_url(v)
            if u:
                return u
        return None
    return None
