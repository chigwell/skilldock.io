# Skilldock MCP

This folder contains a local MCP server/client pair that auto-discovers tools from the installed `skilldock` package at runtime.

## Structure

- `server/skilldock_mcp_server.py`: stdio MCP server
- `client/skilldock_mcp_client.py`: simple CLI MCP client for local usage/testing

## How auto-registration works

The server imports `skilldock.SkilldockClient`, loads the OpenAPI spec through the package, then dynamically maps:

- MCP tool name -> `op.python_name`
- Runtime call -> `client.call_operation(op.operation_id, ...)`

No operation IDs are hardcoded in the MCP layer, so new/changed API operations in `skilldock` are picked up automatically when the server restarts.

## Run server

```bash
python mcp/server/skilldock_mcp_server.py
```

Use an interpreter where `skilldock` (and its dependencies) is installed.

Optional overrides:

```bash
python mcp/server/skilldock_mcp_server.py \
  --openapi-url https://api.skilldock.io/openapi.json \
  --base-url https://api.skilldock.io \
  --token YOUR_TOKEN \
  --timeout-s 30
```

If not provided, values are read from the existing Skilldock config.

## Use local MCP client

List tools:

```bash
python mcp/client/skilldock_mcp_client.py list
```

Call a tool:

```bash
python mcp/client/skilldock_mcp_client.py call some_operation_name --arg id=123
```

Call with JSON body:

```bash
python mcp/client/skilldock_mcp_client.py call create_item \
  --arg json_body='{"name":"demo"}'
```

Call with explicit `params` object:

```bash
python mcp/client/skilldock_mcp_client.py call get_item \
  --arg params='{"id":"123"}'
```

Pass all args as JSON:

```bash
python mcp/client/skilldock_mcp_client.py call get_item \
  --args-json '{"id":"123","auth":true}'
```

Read args JSON from file:

```bash
python mcp/client/skilldock_mcp_client.py call get_item \
  --args-json @/absolute/path/args.json
```
