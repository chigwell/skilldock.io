from __future__ import annotations

import json
from functools import wraps
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx

from .config import DEFAULT_OPENAPI_URL, DEFAULT_TIMEOUT_S
from .openapi import AuthStrategy, OpenAPIOperation, OpenAPISpec, load_openapi, parse_spec


class SkilldockError(RuntimeError):
    pass


class OperationNotFoundError(SkilldockError):
    pass


class AuthRequiredError(SkilldockError):
    pass


@dataclass(frozen=True)
class SkilldockHTTPError(SkilldockError):
    status_code: int
    body: str

    def __str__(self) -> str:  # pragma: no cover
        return f"HTTP {self.status_code}: {self.body}"


def _apply_auth(headers: dict[str, str], auth: AuthStrategy, token: str) -> None:
    if auth.kind == "apiKey-header":
        headers[auth.header] = token
        return
    # Default: Bearer.
    scheme = auth.scheme or "Bearer"
    headers[auth.header] = f"{scheme} {token}".strip()


class OperationsProxy:
    """
    Dynamic attribute-based access to OpenAPI operations.

    Example:
        client.ops.get_item(id="123")
    """

    def __init__(self, client: "SkilldockClient") -> None:
        self._client = client
        self._by_name: dict[str, str] | None = None  # python_name -> operation_id

    def _mapping(self) -> dict[str, str]:
        if self._by_name is None:
            m: dict[str, str] = {}
            for op_id, op in self._client.spec.operations.items():
                # python_name is already made unique in openapi.parse_spec.
                m[op.python_name] = op_id
            self._by_name = m
        return self._by_name

    def __dir__(self) -> list[str]:  # pragma: no cover
        return sorted(set(super().__dir__()) | set(self._mapping().keys()))

    def __getattr__(self, name: str):
        op_id = self._mapping().get(name)
        if not op_id:
            raise AttributeError(name)

        op: OpenAPIOperation = self._client.spec.operations[op_id]

        @wraps(self._client.call_operation)
        def _call(
            *,
            params: dict[str, Any] | None = None,
            json_body: Any | None = None,
            content: bytes | str | None = None,
            data: dict[str, Any] | None = None,
            files: dict[str, Any] | None = None,
            headers: dict[str, str] | None = None,
            auth: bool = True,
            **kwargs: Any,
        ) -> Any:
            # Convenience: allow passing params as kwargs.
            if params is not None and kwargs:
                raise TypeError("Pass either params=... or keyword params, not both.")
            if params is None and kwargs:
                params = kwargs
            return self._client.call_operation(
                op_id,
                params=params,
                json_body=json_body,
                content=content,
                data=data,
                files=files,
                headers=headers,
                auth=auth,
            )

        _call.__name__ = name
        _call.__doc__ = f"{op.method.upper()} {op.path}\n\noperationId: {op.operation_id}\n"
        return _call


class SkilldockClient:
    """
    OpenAPI-driven API client. It loads the OpenAPI spec at runtime and can call any operationId.
    """

    def __init__(
        self,
        *,
        openapi_url: str = DEFAULT_OPENAPI_URL,
        base_url: str | None = None,
        token: str | None = None,
        timeout_s: float = DEFAULT_TIMEOUT_S,
        auth_header: str | None = None,
        auth_scheme: str | None = None,
        default_headers: dict[str, str] | None = None,
    ) -> None:
        self.openapi_url = openapi_url
        self._base_url_override = base_url
        self.token = token
        self.timeout_s = timeout_s
        self._auth_header_override = auth_header
        self._auth_scheme_override = auth_scheme
        self._default_headers = dict(default_headers or {})

        self._http = httpx.Client(timeout=timeout_s, follow_redirects=True)
        self._spec: OpenAPISpec | None = None
        self._ops_proxy: OperationsProxy | None = None

    def close(self) -> None:
        self._http.close()

    def __enter__(self) -> "SkilldockClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    @property
    def spec(self) -> OpenAPISpec:
        if self._spec is None:
            try:
                raw = load_openapi(self.openapi_url, timeout_s=self.timeout_s)
                self._spec = parse_spec(self.openapi_url, raw)
            except Exception as e:  # noqa: BLE001 - wrap into a stable SDK error
                raise SkilldockError(f"Failed to load OpenAPI spec from {self.openapi_url}: {e}") from e
        return self._spec

    @property
    def ops(self) -> OperationsProxy:
        if self._ops_proxy is None:
            self._ops_proxy = OperationsProxy(self)
        return self._ops_proxy

    @property
    def base_url(self) -> str:
        return (self._base_url_override or self.spec.base_url).rstrip("/")

    def operation_ids(self) -> list[str]:
        return sorted(self.spec.operations.keys())

    def get_operation(self, operation_id: str) -> Any:
        try:
            return self.spec.operations[operation_id]
        except KeyError as e:
            raise OperationNotFoundError(f"Unknown operation_id: {operation_id}") from e

    def request(
        self,
        *,
        method: str,
        path: str,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        content: bytes | str | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
    ) -> httpx.Response:
        if content is not None and (json_body is not None or data is not None or files is not None):
            raise SkilldockError("Pass only one of content/json_body/data/files.")
        if path.startswith(("http://", "https://")):
            url = path
        else:
            if not path.startswith("/"):
                path = "/" + path
            url = f"{self.base_url}{path}"

        req_headers = dict(self._default_headers)
        if headers:
            req_headers.update(headers)

        if auth and self.token:
            # If user explicitly configured header/scheme, respect it.
            if self._auth_header_override:
                scheme = self._auth_scheme_override or ""
                value = f"{scheme} {self.token}".strip()
                req_headers[self._auth_header_override] = value
            else:
                auth_strategy = self._spec.auth if self._spec else AuthStrategy(kind="unknown", header="Authorization", scheme="Bearer")
                _apply_auth(req_headers, auth_strategy, self.token)

        try:
            resp = self._http.request(
                method.upper(),
                url,
                params=params,
                json=json_body,
                content=content,
                data=data,
                files=files,
                headers=req_headers,
            )
        except httpx.HTTPError as e:
            raise SkilldockError(f"Request failed: {e}") from e

        if resp.status_code >= 400:
            body = resp.text
            raise SkilldockHTTPError(resp.status_code, body)
        return resp

    def request_operation(
        self,
        operation_id: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        content: bytes | str | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
    ) -> httpx.Response:
        op = self.get_operation(operation_id)
        params = dict(params or {})

        if op.requires_auth and auth and not self.token:
            raise AuthRequiredError(
                f"Operation {operation_id} requires authentication. "
                "Run `skilldock auth login` or `skilldock auth set-token ...` first."
            )

        path = op.path
        query: dict[str, Any] = {}
        header_params: dict[str, str] = {}

        # Spec-defined parameters. Unknown params are treated as query params.
        spec_param_names: set[str] = set()
        for p in op.parameters:
            name = p.get("name")
            loc = p.get("in")
            if not isinstance(name, str) or not isinstance(loc, str):
                continue
            spec_param_names.add(name)

        # Apply path params first.
        for p in op.parameters:
            name = p.get("name")
            loc = p.get("in")
            required = bool(p.get("required", False))
            if not isinstance(name, str) or not isinstance(loc, str):
                continue
            if name not in params:
                if required and loc == "path":
                    raise SkilldockError(f"Missing required path param: {name}")
                continue
            value = params.pop(name)
            if loc == "path":
                path = path.replace("{" + name + "}", quote(str(value), safe=""))
            elif loc == "query":
                query[name] = value
            elif loc == "header":
                header_params[name] = str(value)

        # Any leftover params -> query params (useful when the spec is missing details).
        for k, v in list(params.items()):
            if k in spec_param_names:
                continue
            query[k] = v

        headers_final = dict(headers or {})
        headers_final.update(header_params)

        return self.request(
            method=op.method,
            path=path,
            params=query or None,
            json_body=json_body,
            content=content,
            data=data,
            files=files,
            headers=headers_final or None,
            auth=auth,
        )

    def call_operation(
        self,
        operation_id: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: Any | None = None,
        content: bytes | str | None = None,
        data: dict[str, Any] | None = None,
        files: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        auth: bool = True,
    ) -> Any:
        resp = self.request_operation(
            operation_id,
            params=params,
            json_body=json_body,
            content=content,
            data=data,
            files=files,
            headers=headers,
            auth=auth,
        )
        ctype = resp.headers.get("content-type", "")
        if "application/json" in ctype:
            return resp.json()
        # Try JSON anyway, then fall back.
        try:
            return resp.json()
        except json.JSONDecodeError:
            return resp.text
