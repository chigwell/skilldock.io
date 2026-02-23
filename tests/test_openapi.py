import unittest

from skilldock.openapi import parse_spec


class TestOpenAPIParsing(unittest.TestCase):
    def test_parses_operations_and_auth(self) -> None:
        raw = {
            "openapi": "3.0.0",
            "info": {"title": "t", "version": "1"},
            "servers": [{"url": "https://example.test"}],
            "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
            "security": [{"bearerAuth": []}],
            "paths": {
                "/public": {"get": {"operationId": "PublicGet", "security": []}},
                "/items/{id}": {
                    "parameters": [{"name": "id", "in": "path", "required": True}],
                    "get": {"operationId": "GetItem"},
                },
            },
        }
        spec = parse_spec("https://example.test/openapi.json", raw)
        self.assertEqual(spec.base_url, "https://example.test")
        self.assertEqual(spec.auth.kind, "http-bearer")

        self.assertIn("PublicGet", spec.operations)
        self.assertFalse(spec.operations["PublicGet"].requires_auth)

        self.assertIn("GetItem", spec.operations)
        self.assertTrue(spec.operations["GetItem"].requires_auth)

