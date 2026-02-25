import base64
import io
import json
import unittest
from unittest.mock import patch

import httpx

from skilldock.client import SkilldockClient


def _jwt_with_exp(exp: int) -> str:
    header = base64.urlsafe_b64encode(b'{"alg":"none","typ":"JWT"}').decode("ascii").rstrip("=")
    payload = base64.urlsafe_b64encode(json.dumps({"exp": exp}).encode("utf-8")).decode("ascii").rstrip("=")
    return f"{header}.{payload}.sig"


class TestRedirectAuth(unittest.TestCase):
    def test_authorization_is_kept_on_same_origin_redirect(self) -> None:
        seen: list[tuple[str, str | None]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((str(request.url), request.headers.get("authorization")))
            if request.url.path == "/v1/files/file_1/download":
                return httpx.Response(302, headers={"location": "/v1/files/file_1"})
            return httpx.Response(200, content=b"ok")

        client = SkilldockClient(
            openapi_url="https://api.skilldock.io/openapi.json",
            base_url="https://api.skilldock.io",
            token="tok_123",
        )
        client._http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)  # type: ignore[attr-defined]
        try:
            response = client.request(method="GET", path="/v1/files/file_1/download", auth=True)
        finally:
            client.close()

        self.assertEqual(response.content, b"ok")
        self.assertEqual(seen[0][1], "Bearer tok_123")
        self.assertEqual(seen[1][1], "Bearer tok_123")

    def test_authorization_is_not_forwarded_cross_origin(self) -> None:
        seen: list[tuple[str, str | None]] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen.append((str(request.url), request.headers.get("authorization")))
            if request.url.host == "api.skilldock.io":
                return httpx.Response(302, headers={"location": "https://cdn.example.com/file.zip"})
            return httpx.Response(200, content=b"ok")

        client = SkilldockClient(
            openapi_url="https://api.skilldock.io/openapi.json",
            base_url="https://api.skilldock.io",
            token="tok_123",
        )
        client._http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)  # type: ignore[attr-defined]
        try:
            response = client.request(method="GET", path="/v1/files/file_1/download", auth=True)
        finally:
            client.close()

        self.assertEqual(response.content, b"ok")
        self.assertEqual(seen[0][1], "Bearer tok_123")
        self.assertIsNone(seen[1][1])


class TestOptionalAuthFallback(unittest.TestCase):
    def test_public_request_skips_expired_jwt_and_warns(self) -> None:
        seen_auth: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_auth.append(request.headers.get("authorization"))
            return httpx.Response(200, json={"ok": True})

        client = SkilldockClient(
            openapi_url="https://api.skilldock.io/openapi.json",
            base_url="https://api.skilldock.io",
            token=_jwt_with_exp(1),
        )
        client._http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)  # type: ignore[attr-defined]
        try:
            with patch("sys.stderr", new=io.StringIO()) as stderr:
                resp = client.request(method="GET", path="/v1/skills", auth=True, auth_optional=True)
        finally:
            client.close()

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(seen_auth, [None])
        self.assertIn("warning:", stderr.getvalue())
        self.assertIn("unauthenticated", stderr.getvalue())

    def test_public_request_retries_without_auth_after_401(self) -> None:
        seen_auth: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_auth.append(request.headers.get("authorization"))
            if len(seen_auth) == 1:
                return httpx.Response(401, json={"error": {"code": "unauthorized"}})
            return httpx.Response(200, json={"ok": True})

        client = SkilldockClient(
            openapi_url="https://api.skilldock.io/openapi.json",
            base_url="https://api.skilldock.io",
            token="tok_123",
        )
        client._http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)  # type: ignore[attr-defined]
        try:
            with patch("sys.stderr", new=io.StringIO()) as stderr:
                resp = client.request(method="GET", path="/v1/skills", auth=True, auth_optional=True)
        finally:
            client.close()

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(seen_auth, ["Bearer tok_123", None])
        self.assertIn("retrying without authentication", stderr.getvalue())

    def test_public_request_retries_without_auth_after_500(self) -> None:
        seen_auth: list[str | None] = []

        def handler(request: httpx.Request) -> httpx.Response:
            seen_auth.append(request.headers.get("authorization"))
            if len(seen_auth) == 1:
                return httpx.Response(500, json={"error": {"code": "internal_error"}})
            return httpx.Response(200, json={"ok": True})

        client = SkilldockClient(
            openapi_url="https://api.skilldock.io/openapi.json",
            base_url="https://api.skilldock.io",
            token="tok_123",
        )
        client._http = httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)  # type: ignore[attr-defined]
        try:
            with patch("sys.stderr", new=io.StringIO()) as stderr:
                resp = client.request(method="GET", path="/v1/skills", auth=True, auth_optional=True)
        finally:
            client.close()

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(seen_auth, ["Bearer tok_123", None])
        self.assertIn("warning:", stderr.getvalue())
