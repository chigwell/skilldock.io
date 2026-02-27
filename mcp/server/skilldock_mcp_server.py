#!/usr/bin/env python3
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import sys
from pathlib import Path
from typing import Any

# Support running directly from this repository without installing the package.
_REPO_SRC = Path(__file__).resolve().parents[2] / "src"
if _REPO_SRC.exists() and str(_REPO_SRC) not in sys.path:
    sys.path.insert(0, str(_REPO_SRC))

from skilldock import SkilldockClient
from skilldock.client import SkilldockError, SkilldockHTTPError
from skilldock.config import load_config

MCP_PROTOCOL_VERSION = "2024-11-05"
SERVER_NAME = "skilldock-mcp"


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _json_schema_from_openapi_schema(schema: Any) -> dict[str, Any]:
    if not isinstance(schema, dict):
        return {}

    out: dict[str, Any] = {}
    for key in (
        "type",
        "format",
        "enum",
        "items",
        "properties",
        "required",
        "description",
        "default",
        "minimum",
        "maximum",
        "minLength",
        "maxLength",
        "oneOf",
        "anyOf",
        "allOf",
    ):
        if key in schema:
            out[key] = schema[key]

    if schema.get("nullable"):
        if "type" in out and isinstance(out["type"], str):
            out["type"] = [out["type"], "null"]
        else:
            out["anyOf"] = out.get("anyOf", [])
            out["anyOf"].append({"type": "null"})

    if "$ref" in schema:
        # Keep references as descriptive metadata since tools input schema should stay self-contained.
        out.setdefault("description", f"OpenAPI ref: {schema['$ref']}")
    return out


def _json_schema_for_request_body(op: Any) -> dict[str, Any]:
    request_body = op.request_body if hasattr(op, "request_body") else None
    if not isinstance(request_body, dict):
        return {}
    content = request_body.get("content")
    if not isinstance(content, dict):
        return {}

    for ctype in ("application/json", "application/*+json"):
        media = content.get(ctype)
        if isinstance(media, dict) and isinstance(media.get("schema"), dict):
            return _json_schema_from_openapi_schema(media["schema"])

    for media in content.values():
        if isinstance(media, dict) and isinstance(media.get("schema"), dict):
            return _json_schema_from_openapi_schema(media["schema"])
    return {}


def _normalize_files_arg(value: Any) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise SkilldockError("`files` must be an object.")

    files: dict[str, Any] = {}
    for field_name, file_value in value.items():
        if isinstance(file_value, str):
            if not file_value.startswith("@"):
                raise SkilldockError(
                    f"`files.{field_name}` string values must start with @ and point to a local file path."
                )
            path = Path(file_value[1:]).expanduser()
            if not path.exists() or not path.is_file():
                raise SkilldockError(f"`files.{field_name}` path not found: {path}")
            raw = path.read_bytes()
            ctype, _ = mimetypes.guess_type(str(path))
            files[str(field_name)] = (path.name, raw, ctype or "application/octet-stream")
            continue

        if not isinstance(file_value, dict):
            raise SkilldockError(
                f"`files.{field_name}` must be either '@/path/to/file' or an object with content."
            )

        filename = str(file_value.get("filename") or f"{field_name}.bin")
        content_type = str(file_value.get("content_type") or "application/octet-stream")
        if isinstance(file_value.get("text"), str):
            payload = file_value["text"].encode("utf-8")
        elif isinstance(file_value.get("content_base64"), str):
            try:
                payload = base64.b64decode(file_value["content_base64"], validate=True)
            except Exception as exc:  # noqa: BLE001
                raise SkilldockError(
                    f"`files.{field_name}.content_base64` is not valid base64."
                ) from exc
        else:
            raise SkilldockError(
                f"`files.{field_name}` object must include `text` or `content_base64`."
            )
        files[str(field_name)] = (filename, payload, content_type)
    return files


class StdioMCPServer:
    def __init__(self, client: SkilldockClient) -> None:
        self.client = client
        self._tool_to_operation: dict[str, str] = {}
        self._tool_descriptors: list[dict[str, Any]] = []
        self._registry_error: str | None = None

    def _build_tool_registry(self) -> None:
        self._tool_to_operation.clear()
        self._tool_descriptors.clear()
        self._registry_error = None

        operations = sorted(self.client.spec.operations.values(), key=lambda op: op.python_name)
        for op in operations:
            tool_name = op.python_name
            self._tool_to_operation[tool_name] = op.operation_id

            properties: dict[str, Any] = {
                "params": {
                    "type": "object",
                    "description": "Additional request params keyed by parameter name.",
                    "additionalProperties": True,
                },
                "json_body": _json_schema_for_request_body(op) or {
                    "description": "JSON request body when operation accepts one."
                },
                "data": {
                    "type": "object",
                    "description": "Form fields for form/multipart operations.",
                    "additionalProperties": True,
                },
                "files": {
                    "type": "object",
                    "description": (
                        "Multipart files mapping. Value formats: '@/path/to/file' or "
                        "{filename, content_type?, text? | content_base64?}."
                    ),
                    "additionalProperties": True,
                },
                "headers": {
                    "type": "object",
                    "description": "Additional HTTP headers.",
                    "additionalProperties": {"type": "string"},
                },
                "auth": {
                    "type": "boolean",
                    "description": "Whether to include configured auth token (default true).",
                    "default": True,
                },
            }
            required: list[str] = []
            for param in op.parameters:
                if not isinstance(param, dict):
                    continue
                name = param.get("name")
                location = param.get("in")
                if not isinstance(name, str) or not isinstance(location, str):
                    continue

                schema = _json_schema_from_openapi_schema(param.get("schema"))
                if not schema:
                    schema = {"type": "string"}
                schema.setdefault("description", f"OpenAPI {location} parameter `{name}`.")
                properties[name] = schema
                if bool(param.get("required")):
                    required.append(name)

            description_parts = [f"{op.method.upper()} {op.path}", f"operationId: {op.operation_id}"]
            if op.summary:
                description_parts.append(op.summary)
            self._tool_descriptors.append(
                {
                    "name": tool_name,
                    "description": " | ".join(description_parts),
                    "inputSchema": {
                        "type": "object",
                        "properties": properties,
                        "required": sorted(set(required)),
                        "additionalProperties": True,
                    },
                }
            )

    def _ensure_tool_registry(self) -> None:
        if self._tool_descriptors or self._tool_to_operation:
            return
        try:
            self._build_tool_registry()
        except Exception as exc:  # noqa: BLE001
            self._registry_error = (
                f"Failed to discover Skilldock operations from OpenAPI: {exc}. "
                "Check --openapi-url/--base-url and network access."
            )

    def _result_payload(self, value: Any, *, is_error: bool = False) -> dict[str, Any]:
        if isinstance(value, (dict, list)):
            text = json.dumps(value, indent=2, ensure_ascii=False)
            payload: dict[str, Any] = {
                "content": [{"type": "text", "text": text}],
                "structuredContent": value,
            }
        else:
            payload = {"content": [{"type": "text", "text": str(value)}]}
        if is_error:
            payload["isError"] = True
        return payload

    def _call_tool(self, name: str, arguments: Any) -> dict[str, Any]:
        self._ensure_tool_registry()
        if self._registry_error:
            return self._result_payload(self._registry_error, is_error=True)
        op_id = self._tool_to_operation.get(name)
        if not op_id:
            return self._result_payload(f"Unknown tool: {name}", is_error=True)
        if arguments is None:
            arguments = {}
        if not isinstance(arguments, dict):
            return self._result_payload("Tool arguments must be an object.", is_error=True)

        reserved = {"params", "json_body", "content", "data", "files", "headers", "auth"}
        params = arguments.get("params")
        if params is None:
            merged_params: dict[str, Any] = {}
        elif isinstance(params, dict):
            merged_params = dict(params)
        else:
            return self._result_payload("`params` must be an object when provided.", is_error=True)
        for key, value in arguments.items():
            if key not in reserved:
                merged_params[key] = value

        json_body = arguments.get("json_body")
        content = arguments.get("content")
        data = arguments.get("data")
        files = arguments.get("files")
        headers = arguments.get("headers")
        auth = bool(arguments.get("auth", True))

        if data is not None and not isinstance(data, dict):
            return self._result_payload("`data` must be an object when provided.", is_error=True)
        if headers is not None and not isinstance(headers, dict):
            return self._result_payload("`headers` must be an object when provided.", is_error=True)

        try:
            result = self.client.call_operation(
                op_id,
                params=merged_params or None,
                json_body=json_body,
                content=content,
                data=data,
                files=_normalize_files_arg(files),
                headers=headers,
                auth=auth,
            )
            return self._result_payload(result)
        except SkilldockHTTPError as exc:
            return self._result_payload(f"HTTP {exc.status_code}: {exc.body}", is_error=True)
        except SkilldockError as exc:
            return self._result_payload(str(exc), is_error=True)
        except Exception as exc:  # noqa: BLE001
            return self._result_payload(f"Unexpected error: {exc}", is_error=True)

    def _make_response(self, request_id: Any, result: Any) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def _make_error(self, request_id: Any, code: int, message: str) -> dict[str, Any]:
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    def _handle(self, message: dict[str, Any]) -> dict[str, Any] | None:
        request_id = message.get("id")
        method = message.get("method")
        params = message.get("params")

        if not isinstance(method, str):
            if request_id is None:
                return None
            return self._make_error(request_id, -32600, "Invalid request: missing method.")

        if method in {"notifications/initialized", "initialized"}:
            return None

        if method == "ping":
            if request_id is None:
                return None
            return self._make_response(request_id, {})

        if method == "initialize":
            if request_id is None:
                return None
            return self._make_response(
                request_id,
                {
                    "protocolVersion": MCP_PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": SERVER_NAME, "version": "1.0.0"},
                },
            )

        if method == "tools/list":
            if request_id is None:
                return None
            self._ensure_tool_registry()
            if self._registry_error:
                return self._make_response(request_id, {"tools": []})
            return self._make_response(request_id, {"tools": self._tool_descriptors})

        if method == "tools/call":
            if request_id is None:
                return None
            if not isinstance(params, dict):
                return self._make_error(request_id, -32602, "Invalid params for tools/call.")
            name = params.get("name")
            if not isinstance(name, str):
                return self._make_error(request_id, -32602, "tools/call requires a string `name`.")
            arguments = params.get("arguments")
            result = self._call_tool(name, arguments)
            return self._make_response(request_id, result)

        if request_id is None:
            return None
        return self._make_error(request_id, -32601, f"Method not found: {method}")

    @staticmethod
    def _read_message() -> dict[str, Any] | None:
        headers: dict[str, str] = {}
        while True:
            line = sys.stdin.buffer.readline()
            if not line:
                return None
            stripped = line.strip()
            if not stripped:
                break
            if b":" not in line:
                continue
            key, value = line.decode("utf-8", errors="replace").split(":", 1)
            headers[key.strip().lower()] = value.strip()

        length_raw = headers.get("content-length")
        if not length_raw:
            return None
        try:
            length = int(length_raw)
        except ValueError:
            return None
        if length <= 0:
            return None

        body = sys.stdin.buffer.read(length)
        if not body:
            return None
        try:
            parsed = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _write_message(payload: dict[str, Any]) -> None:
        body = _json_dumps(payload).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        sys.stdout.buffer.write(header)
        sys.stdout.buffer.write(body)
        sys.stdout.buffer.flush()

    def run(self) -> None:
        while True:
            message = self._read_message()
            if message is None:
                break
            response = self._handle(message)
            if response is not None:
                self._write_message(response)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Skilldock MCP server (stdio).")
    parser.add_argument(
        "--openapi-url",
        default=None,
        help="OpenAPI URL/path override. Defaults to Skilldock CLI config.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Base URL override. Defaults to Skilldock CLI config.",
    )
    parser.add_argument(
        "--token",
        default=None,
        help="Token override. Defaults to Skilldock CLI config or SKILLDOCK_TOKEN.",
    )
    parser.add_argument(
        "--timeout-s",
        type=float,
        default=None,
        help="Request timeout override in seconds.",
    )
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    cfg = load_config()

    client = SkilldockClient(
        openapi_url=args.openapi_url or cfg.openapi_url,
        base_url=args.base_url or cfg.base_url,
        token=args.token or cfg.token,
        timeout_s=args.timeout_s or cfg.timeout_s,
        auth_header=cfg.auth_header,
        auth_scheme=cfg.auth_scheme,
    )
    server = StdioMCPServer(client)
    try:
        server.run()
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
