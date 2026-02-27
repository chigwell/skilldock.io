#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any


def _json_dumps(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, separators=(",", ":"))


def _read_message(stream) -> dict[str, Any] | None:
    headers: dict[str, str] = {}
    while True:
        line = stream.readline()
        if not line:
            return None
        stripped = line.strip()
        if not stripped:
            break
        if b":" not in line:
            continue
        key, value = line.decode("utf-8", errors="replace").split(":", 1)
        headers[key.strip().lower()] = value.strip()

    raw_length = headers.get("content-length")
    if not raw_length:
        return None
    try:
        length = int(raw_length)
    except ValueError:
        return None
    if length <= 0:
        return None

    body = stream.read(length)
    if not body:
        return None
    parsed = json.loads(body.decode("utf-8"))
    return parsed if isinstance(parsed, dict) else None


def _write_message(stream, payload: dict[str, Any]) -> None:
    body = _json_dumps(payload).encode("utf-8")
    stream.write(f"Content-Length: {len(body)}\r\n\r\n".encode("ascii"))
    stream.write(body)
    stream.flush()


def _jsonish(value: str) -> Any:
    value = value.strip()
    if value == "":
        return ""
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def _parse_kv(items: list[str]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"Expected key=value, got: {item}")
        key, value = item.split("=", 1)
        out[key] = _jsonish(value)
    return out


class MCPProcessClient:
    def __init__(self, server_cmd: list[str]) -> None:
        self.server_cmd = server_cmd
        self._proc: subprocess.Popen[bytes] | None = None
        self._next_id = 1

    def __enter__(self) -> "MCPProcessClient":
        self._proc = subprocess.Popen(
            self.server_cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
        )
        self.request(
            "initialize",
            {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "skilldock-mcp-client", "version": "1.0.0"},
            },
        )
        self.notify("notifications/initialized", {})
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._proc is not None:
            if self._proc.stdin:
                self._proc.stdin.close()
            self._proc.terminate()
            self._proc.wait(timeout=2)

    @property
    def _stdin(self):
        if self._proc is None or self._proc.stdin is None:
            raise RuntimeError("Client is not started.")
        return self._proc.stdin

    @property
    def _stdout(self):
        if self._proc is None or self._proc.stdout is None:
            raise RuntimeError("Client is not started.")
        return self._proc.stdout

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        request_id = self._next_id
        self._next_id += 1
        payload: dict[str, Any] = {"jsonrpc": "2.0", "id": request_id, "method": method}
        if params is not None:
            payload["params"] = params
        _write_message(self._stdin, payload)

        while True:
            response = _read_message(self._stdout)
            if response is None:
                raise RuntimeError("No MCP response from server.")
            if response.get("id") != request_id:
                # Ignore unrelated messages.
                continue
            if "error" in response:
                raise RuntimeError(f"MCP error: {response['error']}")
            return response.get("result")

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        payload: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            payload["params"] = params
        _write_message(self._stdin, payload)

    def list_tools(self) -> list[dict[str, Any]]:
        result = self.request("tools/list")
        if not isinstance(result, dict):
            return []
        tools = result.get("tools")
        return tools if isinstance(tools, list) else []

    def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        result = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        return result if isinstance(result, dict) else {"content": [{"type": "text", "text": str(result)}]}


def _default_server_cmd() -> list[str]:
    server_script = (
        Path(__file__).resolve().parents[1] / "server" / "skilldock_mcp_server.py"
    )
    return [sys.executable, str(server_script)]


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal client for the local Skilldock MCP server.")
    parser.add_argument(
        "--server-cmd",
        nargs="+",
        default=_default_server_cmd(),
        help="Command used to start the MCP server process.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    list_parser = subparsers.add_parser("list", help="List available tools.")
    list_parser.add_argument("--json", action="store_true", help="Print raw JSON output.")

    call = subparsers.add_parser("call", help="Call a tool by name.")
    call.add_argument("tool_name", help="MCP tool name.")
    call.add_argument("--json", action="store_true", help="Print raw JSON output.")
    call.add_argument(
        "--arg",
        action="append",
        default=[],
        help="Tool argument as key=value (value may be JSON). Repeatable.",
    )
    call.add_argument(
        "--args-json",
        default=None,
        help="Tool arguments as JSON object string or @/path/to/file.json.",
    )
    return parser


def _load_args_json(raw: str | None) -> dict[str, Any]:
    if not raw:
        return {}
    candidate = raw.strip()
    if candidate.startswith("@"):
        payload = Path(candidate[1:]).expanduser().read_text(encoding="utf-8")
    else:
        payload = candidate
    parsed = json.loads(payload)
    if not isinstance(parsed, dict):
        raise ValueError("--args-json must be a JSON object.")
    return parsed


def _render_tool_result(result: dict[str, Any]) -> str:
    content = result.get("content")
    if isinstance(content, list):
        texts: list[str] = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text" and isinstance(item.get("text"), str):
                texts.append(item["text"])
        if texts:
            return "\n".join(texts)
    return json.dumps(result, indent=2, ensure_ascii=False)


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()

    with MCPProcessClient(args.server_cmd) as client:
        if args.command == "list":
            tools = client.list_tools()
            if args.json:
                print(json.dumps({"tools": tools}, indent=2, ensure_ascii=False))
            else:
                for tool in tools:
                    name = tool.get("name", "")
                    description = tool.get("description", "")
                    print(f"{name}\t{description}")
            return 0

        if args.command == "call":
            arguments = _load_args_json(args.args_json)
            cli_args = _parse_kv(args.arg)
            overlap = set(arguments).intersection(cli_args)
            if overlap:
                parser.error(
                    f"Duplicate argument keys in --arg and --args-json: {', '.join(sorted(overlap))}"
                )
            arguments.update(cli_args)
            result = client.call_tool(args.tool_name, arguments)
            if args.json:
                print(json.dumps(result, indent=2, ensure_ascii=False))
            else:
                print(_render_tool_result(result))
            return 0

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
