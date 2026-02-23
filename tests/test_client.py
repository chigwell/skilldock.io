import unittest

import httpx

from skilldock.client import SkilldockClient


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
