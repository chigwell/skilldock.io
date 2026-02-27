import io
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from skilldock.cli import _format_http_error, _make_runtime_client, build_parser, cmd_install, cmd_skill, cmd_skills, cmd_users, main
from skilldock.client import SkilldockError, SkilldockHTTPError
from skilldock.config import DEFAULT_OPENAPI_URL, Config


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class TestSkillsSearch(unittest.TestCase):
    def test_search_uses_configured_token_and_auth_enabled(self) -> None:
        args = build_parser().parse_args(["skills", "search", "docker", "--json"])
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )

        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()),
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse({"items": []})
            rc = cmd_skills(args)

        self.assertEqual(rc, 0)
        self.assertEqual(mock_client_cls.call_args.kwargs["token"], "tok_123")
        self.assertTrue(mock_client.request.call_args.kwargs["auth"])
        self.assertTrue(mock_client.request.call_args.kwargs["auth_optional"])
        self.assertEqual(mock_client.request.call_args.kwargs["method"], "POST")
        self.assertEqual(mock_client.request.call_args.kwargs["path"], "/v2/search")
        self.assertEqual(
            mock_client.request.call_args.kwargs["json_body"],
            {"query": "docker", "rewrite_query": True},
        )

    def test_get_prefers_latest_release_description_md(self) -> None:
        args = build_parser().parse_args(["skills", "get", "acme/my-skill"])
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )

        payload = {
            "skill": {
                "title": "My Skill",
                "description_md": "legacy-skill-desc",
                "latest_release": {"version": "0.1.1", "description_md": "release-desc"},
                "download_stats": {"total": 1200, "last_week": 230, "last_month": 810},
                "first_release_created_at": "2026-01-15T08:30:00.000Z",
            }
        }
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()) as stdout,
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_skills(args)

        self.assertEqual(rc, 0)
        self.assertTrue(mock_client.request.call_args.kwargs["auth_optional"])
        out = stdout.getvalue()
        self.assertIn("description_source: latest_release.description_md", out)
        self.assertIn("created_at: 2026-01-15T08:30:00.000Z", out)
        self.assertIn("  total: 1200", out)
        self.assertIn("  last_week: 230", out)
        self.assertIn("  last_month: 810", out)
        self.assertIn("release-desc", out)
        self.assertNotIn("legacy-skill-desc", out)

    def test_release_falls_back_to_skill_description_md(self) -> None:
        args = build_parser().parse_args(["skills", "release", "acme/my-skill", "0.1.0"])
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )

        release_payload = {
            "skill": {
                "download_stats": {"total": 1200, "last_week": 230, "last_month": 810},
                "first_release_created_at": "2026-01-15T08:30:00.000Z",
            },
            "release": {
                "version": "0.1.0",
                "description_md": "",
                "download_stats": {"total": 340, "last_week": 70, "last_month": 190},
            },
        }
        skill_payload = {"skill": {"description_md": "fallback-desc"}}
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()) as stdout,
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.side_effect = [_FakeResponse(release_payload), _FakeResponse(skill_payload)]
            rc = cmd_skills(args)

        self.assertEqual(rc, 0)
        out = stdout.getvalue()
        self.assertTrue(all(call.kwargs.get("auth_optional") for call in mock_client.request.call_args_list))
        self.assertIn("description_source: skill.description_md", out)
        self.assertIn("created_at: 2026-01-15T08:30:00.000Z", out)
        self.assertIn("  total: 1200", out)
        self.assertIn("  last_week: 230", out)
        self.assertIn("  last_month: 810", out)
        self.assertIn("downloads_this_release: 340", out)
        self.assertIn("fallback-desc", out)
        self.assertEqual(mock_client.request.call_count, 2)

    def test_get_uses_na_and_zero_fallbacks_for_missing_stats(self) -> None:
        args = build_parser().parse_args(["skills", "get", "acme/my-skill"])
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )

        payload = {
            "skill": {
                "title": "My Skill",
                "latest_release": {"version": "0.1.1", "description_md": "release-desc"},
                "first_release_created_at": None,
            }
        }
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()) as stdout,
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_skills(args)

        self.assertEqual(rc, 0)
        out = stdout.getvalue()
        self.assertIn("created_at: N/A", out)
        self.assertIn("  total: 0", out)
        self.assertIn("  last_week: 0", out)
        self.assertIn("  last_month: 0", out)

    def test_get_prints_homepage_url_when_present(self) -> None:
        args = build_parser().parse_args(["skills", "get", "acme/my-skill"])
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        payload = {
            "skill": {
                "title": "My Skill",
                "homepage_url": "https://example.com",
                "latest_release": {"version": "0.1.1", "description_md": "release-desc"},
            }
        }
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()) as stdout,
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_skills(args)

        self.assertEqual(rc, 0)
        self.assertIn("homepage_url: https://example.com", stdout.getvalue())

    def test_get_prints_author_fields_when_present(self) -> None:
        args = build_parser().parse_args(["skills", "get", "acme/my-skill"])
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        payload = {
            "skill": {
                "title": "My Skill",
                "author": {
                    "user_id": 123,
                    "display_name": "Jane Doe",
                    "google_picture": "https://cdn.example.com/avatar.jpg",
                },
                "latest_release": {"version": "0.1.1", "description_md": "release-desc"},
            }
        }
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()) as stdout,
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_skills(args)

        self.assertEqual(rc, 0)
        out = stdout.getvalue()
        self.assertIn("author_user_id: 123", out)
        self.assertIn("author_display_name: Jane Doe", out)
        self.assertIn("author_google_picture: https://cdn.example.com/avatar.jpg", out)

    def test_search_renders_latest_releases_column(self) -> None:
        args = build_parser().parse_args(["skills", "search", "docker"])
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        payload = {
            "items": [
                {
                    "namespace": "acme",
                    "slug": "my-skill",
                    "title": "My Skill",
                    "updated_at": "2026-02-14T10:00:00Z",
                    "sale": {"price_usd": "12.00", "sold_total": 10, "can_buy": True},
                    "tags": ["docker", "cli"],
                    "author": {"user_id": 123},
                    "latest_releases": [{"version": "1.2.0"}, {"version": "1.1.0"}],
                }
            ]
        }
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()) as stdout,
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_skills(args)

        self.assertEqual(rc, 0)
        out = stdout.getvalue()
        self.assertIn("LATEST_VERSIONS", out)
        self.assertIn("1.2.0,1.1.0", out)
        self.assertIn("12.00", out)
        self.assertIn("10", out)
        self.assertIn("acme/my-skill (u:123)", out)

    def test_get_renders_access_and_sale_blocks(self) -> None:
        args = build_parser().parse_args(["skills", "get", "acme/my-skill"])
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        payload = {
            "skill": {
                "title": "My Skill",
                "description_md": "paid summary",
                "latest_release": None,
                "access": {
                    "can_view_full_content": False,
                    "is_owner": False,
                    "is_buyer": True,
                    "can_buy": False,
                },
                "sale": {"is_for_sale": True, "price_usd": "12.00", "sold_total": 10, "can_buy": False},
            }
        }
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()) as stdout,
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_skills(args)

        self.assertEqual(rc, 0)
        out = stdout.getvalue()
        self.assertIn("can_view_full_content: false", out)
        self.assertIn("is_buyer: true", out)
        self.assertIn("is_for_sale: true", out)
        self.assertIn("pricing_mode:", out)
        self.assertIn("price_usd: 12.00", out)
        self.assertIn("price_ton:", out)
        self.assertIn("price_ton_nano:", out)

    def test_release_prints_author_fields_when_present(self) -> None:
        args = build_parser().parse_args(["skills", "release", "acme/my-skill", "0.1.0"])
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )

        release_payload = {
            "skill": {
                "author": {
                    "user_id": 123,
                    "display_name": "Jane Doe",
                    "google_picture": "https://cdn.example.com/avatar.jpg",
                }
            },
            "release": {
                "version": "0.1.0",
                "description_md": "desc",
            },
        }
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()) as stdout,
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(release_payload)
            rc = cmd_skills(args)

        self.assertEqual(rc, 0)
        out = stdout.getvalue()
        self.assertIn("author_user_id: 123", out)
        self.assertIn("author_display_name: Jane Doe", out)
        self.assertIn("author_google_picture: https://cdn.example.com/avatar.jpg", out)

    def test_search_maps_per_page_to_max_num_results(self) -> None:
        args = build_parser().parse_args(["skills", "search", "docker", "--per-page", "7", "--json"])
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()),
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse({"items": []})
            rc = cmd_skills(args)

        self.assertEqual(rc, 0)
        self.assertEqual(
            mock_client.request.call_args.kwargs["json_body"],
            {"query": "docker", "rewrite_query": True, "max_num_results": 7},
        )

    def test_releases_calls_paginated_endpoint(self) -> None:
        args = build_parser().parse_args(["skills", "releases", "acme/my-skill", "--page", "2", "--per-page", "10"])
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        payload = {"page": 2, "per_page": 10, "has_more": True, "items": [{"version": "1.0.0"}]}
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()) as stdout,
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_skills(args)

        self.assertEqual(rc, 0)
        out = stdout.getvalue()
        self.assertIn("has_more: true", out)
        self.assertIn("1.0.0", out)
        self.assertEqual(
            mock_client.request.call_args.kwargs["path"],
            "/v1/skills/acme/my-skill/releases",
        )
        self.assertEqual(
            mock_client.request.call_args.kwargs["params"],
            {"page": 2, "per_page": 10},
        )


class TestSkillUpload(unittest.TestCase):
    def test_upload_passes_private_visibility_query_param(self) -> None:
        args = build_parser().parse_args(
            [
                "skill",
                "upload",
                "--namespace",
                "acme",
                "--slug",
                "my-skill",
                "--path",
                ".",
                "--visibility",
                "private",
                "--json",
            ]
        )
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        fake_pkg = SimpleNamespace(
            root=Path("."),
            file_count=1,
            size_bytes=42,
            sha256="abc123",
            warnings=[],
            zip_bytes=b"zip",
        )

        with (
            patch("skilldock.cli.package_skill", return_value=fake_pkg),
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()),
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse({"release": {"version": "1.2.3"}})
            rc = cmd_skill(args)

        self.assertEqual(rc, 0)
        self.assertEqual(mock_client.request.call_args.kwargs["params"]["visibility"], "private")

    def test_upload_omits_visibility_when_not_set(self) -> None:
        args = build_parser().parse_args(
            [
                "skill",
                "upload",
                "--namespace",
                "acme",
                "--slug",
                "my-skill",
                "--path",
                ".",
                "--json",
            ]
        )
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        fake_pkg = SimpleNamespace(
            root=Path("."),
            file_count=1,
            size_bytes=42,
            sha256="abc123",
            warnings=[],
            zip_bytes=b"zip",
        )

        with (
            patch("skilldock.cli.package_skill", return_value=fake_pkg),
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()),
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse({"release": {"version": "1.2.3"}})
            rc = cmd_skill(args)

        self.assertEqual(rc, 0)
        self.assertIsNone(mock_client.request.call_args.kwargs["params"])

    def test_upload_raises_clear_message_on_version_conflict(self) -> None:
        args = build_parser().parse_args(
            [
                "skill",
                "upload",
                "--namespace",
                "acme",
                "--slug",
                "my-skill",
                "--version",
                "0.1.0",
                "--path",
                ".",
                "--json",
            ]
        )
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        fake_pkg = SimpleNamespace(
            root=Path("."),
            file_count=1,
            size_bytes=42,
            sha256="abc123",
            warnings=[],
            zip_bytes=b"zip",
        )

        with (
            patch("skilldock.cli.package_skill", return_value=fake_pkg),
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.side_effect = SkilldockHTTPError(409, '{"message":"version already exists"}')
            with self.assertRaises(SkilldockError) as ctx:
                cmd_skill(args)

        self.assertIn("immutable", str(ctx.exception))
        self.assertIn("0.1.0", str(ctx.exception))

    def test_upload_passes_homepage_url_as_query_param(self) -> None:
        args = build_parser().parse_args(
            [
                "skill",
                "upload",
                "--namespace",
                "acme",
                "--slug",
                "my-skill",
                "--path",
                ".",
                "--homepage-url",
                "https://example.com",
                "--json",
            ]
        )
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        fake_pkg = SimpleNamespace(
            root=Path("."),
            file_count=1,
            size_bytes=42,
            sha256="abc123",
            warnings=[],
            zip_bytes=b"zip",
        )

        with (
            patch("skilldock.cli.package_skill", return_value=fake_pkg),
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()),
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse({"release": {"version": "1.2.3"}})
            rc = cmd_skill(args)

        self.assertEqual(rc, 0)
        self.assertEqual(mock_client.request.call_args.kwargs["params"]["homepage_url"], "https://example.com")

    def test_upload_rejects_non_http_scheme_homepage_url(self) -> None:
        args = build_parser().parse_args(
            [
                "skill",
                "upload",
                "--namespace",
                "acme",
                "--slug",
                "my-skill",
                "--path",
                ".",
                "--homepage-url",
                "ftp://example.com",
                "--json",
            ]
        )

        with self.assertRaises(SkilldockError) as ctx:
            cmd_skill(args)

        self.assertIn("http/https", str(ctx.exception))


class TestInstallShorthand(unittest.TestCase):
    def test_install_accepts_version_shorthand_in_skill_argument(self) -> None:
        args = build_parser().parse_args(["install", "acme/my-skill@1.2.3", "--json"])
        fake_result = SimpleNamespace(
            installed=(),
            updated=(),
            removed=(),
            unchanged=(),
            warnings=(),
            manifest_path=Path("/tmp/.skilldock.json"),
            lock_path=Path("/tmp/.skilldock.lock.json"),
        )
        fake_client = SimpleNamespace(close=lambda: None)
        fake_manager = Mock()
        fake_manager.install.return_value = fake_result

        with (
            patch("skilldock.cli._make_runtime_client", return_value=fake_client),
            patch("skilldock.cli.ApiReleaseRepository"),
            patch("skilldock.cli.LocalSkillManager", return_value=fake_manager),
            patch("sys.stdout", new=io.StringIO()),
        ):
            rc = cmd_install(args)

        self.assertEqual(rc, 0)
        fake_manager.install.assert_called_once_with(skill="acme/my-skill", requirement="1.2.3")

    def test_install_rejects_both_shorthand_and_flag_version(self) -> None:
        args = build_parser().parse_args(["install", "acme/my-skill@1.2.3", "--version", "2.0.0"])

        with self.assertRaises(SkilldockError) as ctx:
            cmd_install(args)

        self.assertIn("either as @<version> or --version", str(ctx.exception))

    def test_install_parser_accepts_verbose_errors_flag(self) -> None:
        args = build_parser().parse_args(["install", "acme/my-skill", "--verbose-errors"])
        self.assertTrue(args.verbose_errors)

    def test_main_install_verbose_errors_prints_cause_chain(self) -> None:
        def _raise_nested(*_args, **_kwargs):
            http_err = SkilldockHTTPError(404, '{"detail":"missing"}')
            inner = SkilldockError("Skill not found or not visible: acme/my-skill")
            inner.__cause__ = http_err
            outer = SkilldockError("Could not resolve dependency graph. Last error: Skill not found or not visible: acme/my-skill")
            outer.__cause__ = inner
            raise outer

        with (
            patch("skilldock.cli.cmd_install", side_effect=_raise_nested),
            patch("sys.stderr", new=io.StringIO()) as stderr,
        ):
            rc = main(["install", "acme/my-skill", "--verbose-errors"])

        self.assertEqual(rc, 1)
        err = stderr.getvalue()
        self.assertIn("error: Could not resolve dependency graph.", err)
        self.assertIn("error_details:", err)
        self.assertIn("cause[1]: SkilldockError: Skill not found or not visible: acme/my-skill", err)
        self.assertIn("cause[2]: SkilldockHTTPError: HTTP 404 Not Found.", err)


class TestHelpCommand(unittest.TestCase):
    def test_help_aliases_parse(self) -> None:
        self.assertEqual(build_parser().parse_args(["help"]).cmd, "help")
        self.assertEqual(build_parser().parse_args(["h"]).cmd, "h")

    def test_main_help_prints_friendly_overview(self) -> None:
        with patch("sys.stdout", new=io.StringIO()) as stdout:
            rc = main(["help"])

        self.assertEqual(rc, 0)
        out = stdout.getvalue()
        self.assertIn("SkillDock CLI (skilldock)", out)
        self.assertIn("What you can do:", out)
        self.assertIn("skilldock skills search docker", out)
        self.assertIn("skilldock help <command>", out)

    def test_main_h_alias_prints_friendly_overview(self) -> None:
        with patch("sys.stdout", new=io.StringIO()) as stdout:
            rc = main(["h"])

        self.assertEqual(rc, 0)
        self.assertIn("SkillDock CLI (skilldock)", stdout.getvalue())

    def test_help_topic_prints_argparse_help_for_command(self) -> None:
        with patch("sys.stdout", new=io.StringIO()) as stdout:
            rc = main(["help", "skills"])

        self.assertEqual(rc, 0)
        out = stdout.getvalue()
        self.assertIn("usage: skilldock skills", out)
        self.assertIn("search              Search skills", out)


class TestHttpErrorFormatting(unittest.TestCase):
    def test_format_409_price_mode_incompatible_flat_code(self) -> None:
        err = SkilldockHTTPError(
            409,
            '{"code":"price_mode_incompatible","message":"fixed_ton buy is not supported yet"}',
        )
        msg = _format_http_error(err)
        self.assertIn("HTTP 409 Conflict. Price mode is incompatible with selected payment provider", msg)
        self.assertIn("fixed_ton buy is not supported yet", msg)

    def test_format_409_price_mode_incompatible_nested_error_code(self) -> None:
        err = SkilldockHTTPError(
            409,
            '{"error":{"code":"price_mode_incompatible","detail":"TON checkout coming next"}}',
        )
        msg = _format_http_error(err)
        self.assertIn("HTTP 409 Conflict. Price mode is incompatible with selected payment provider", msg)
        self.assertIn("TON checkout coming next", msg)

    def test_format_409_payment_provider_unsupported(self) -> None:
        err = SkilldockHTTPError(
            409,
            '{"error":{"code":"payment_provider_unsupported","message":"Only TON is supported"}}',
        )
        msg = _format_http_error(err)
        self.assertIn("HTTP 409 Conflict. Payment provider is unsupported", msg)
        self.assertIn("Only TON is supported", msg)


class TestRuntimeClient(unittest.TestCase):
    def test_make_runtime_client_keeps_configured_token(self) -> None:
        args = SimpleNamespace(openapi_url=None, base_url=None, token=None, timeout_s=None)
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )

        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
        ):
            _make_runtime_client(args)

        self.assertEqual(mock_client_cls.call_args.kwargs["token"], "tok_123")


class TestUsersGet(unittest.TestCase):
    def test_users_get_calls_user_profile_endpoint_and_renders_skills(self) -> None:
        args = build_parser().parse_args(["users", "get", "123"])
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        payload = {
            "user": {"id": 123, "display_name": "Jane Doe", "google_picture": "https://cdn.example.com/avatar.jpg"},
            "skills": {
                "page": 1,
                "per_page": 20,
                "has_more": False,
                "items": [
                    {
                        "namespace": "acme",
                        "slug": "my-skill",
                        "title": "My Skill",
                        "updated_at": "2026-02-15T12:00:00Z",
                        "sale": {"price_usd": "12.00", "sold_total": 10, "can_buy": True},
                    }
                ],
            },
        }
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()) as stdout,
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_users(args)

        self.assertEqual(rc, 0)
        self.assertEqual(mock_client.request.call_args.kwargs["path"], "/v1/user/123")
        self.assertEqual(mock_client.request.call_args.kwargs["params"], {"page": 1, "per_page": 20})
        self.assertTrue(mock_client.request.call_args.kwargs["auth_optional"])
        out = stdout.getvalue()
        self.assertIn("user_id: 123", out)
        self.assertIn("display_name: Jane Doe", out)
        self.assertIn("skills_has_more: false", out)
        self.assertIn("acme/my-skill", out)
        self.assertIn("12.00", out)
        self.assertIn("10", out)


class TestSkillsCommerce(unittest.TestCase):
    def test_set_ton_wallet_calls_endpoint(self) -> None:
        args = build_parser().parse_args(
            ["skills", "set-ton-wallet", "--ton-wallet-address", "UQ123"]
        )
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        payload = {"method": {"id": 13, "kind": "ton_wallet", "ton_wallet_address": "UQ123", "status": "active"}}
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()),
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_skills(args)
        self.assertEqual(rc, 0)
        self.assertEqual(mock_client.request.call_args.kwargs["method"], "POST")
        self.assertEqual(mock_client.request.call_args.kwargs["path"], "/v1/me/payout-methods/ton")
        self.assertEqual(
            mock_client.request.call_args.kwargs["json_body"],
            {"ton_wallet_address": "UQ123"},
        )

    def test_set_price_calls_endpoint(self) -> None:
        args = build_parser().parse_args(
            ["skills", "set-price", "acme/my-skill", "--price-usd", "12.00"]
        )
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        payload = {"price": {"id": 8, "price_usd": "12.00", "created_at": "2026-02-21T10:05:00.000Z"}}
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()),
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_skills(args)
        self.assertEqual(rc, 0)
        self.assertEqual(mock_client.request.call_args.kwargs["method"], "POST")
        self.assertEqual(mock_client.request.call_args.kwargs["path"], "/v1/skills/acme/my-skill/prices")
        self.assertEqual(
            mock_client.request.call_args.kwargs["json_body"],
            {"pricing_mode": "fixed_usd", "price_usd": "12.00"},
        )

    def test_set_price_fixed_usd_explicit_mode_calls_endpoint(self) -> None:
        args = build_parser().parse_args(
            ["skills", "set-price", "acme/my-skill", "--pricing-mode", "fixed_usd", "--price-usd", "12.00"]
        )
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        payload = {
            "price": {
                "id": 8,
                "pricing_mode": "fixed_usd",
                "price_usd": "12.00",
                "price_ton": None,
                "price_ton_nano": None,
                "created_at": "2026-02-21T10:05:00.000Z",
            }
        }
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()),
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_skills(args)
        self.assertEqual(rc, 0)
        self.assertEqual(
            mock_client.request.call_args.kwargs["json_body"],
            {"pricing_mode": "fixed_usd", "price_usd": "12.00"},
        )

    def test_set_price_fixed_ton_calls_endpoint(self) -> None:
        args = build_parser().parse_args(
            ["skills", "set-price", "acme/my-skill", "--pricing-mode", "fixed_ton", "--price-ton", "2.750000000"]
        )
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        payload = {
            "price": {
                "id": 9,
                "pricing_mode": "fixed_ton",
                "price_usd": None,
                "price_ton": "2.750000000",
                "price_ton_nano": 2750000000,
                "created_at": "2026-02-26T12:00:00.000Z",
            }
        }
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()),
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_skills(args)
        self.assertEqual(rc, 0)
        self.assertEqual(mock_client.request.call_args.kwargs["path"], "/v1/skills/acme/my-skill/prices")
        self.assertEqual(
            mock_client.request.call_args.kwargs["json_body"],
            {"pricing_mode": "fixed_ton", "price_ton": "2.750000000"},
        )

    def test_set_commerce_calls_endpoint(self) -> None:
        args = build_parser().parse_args(
            [
                "skills",
                "set-commerce",
                "acme/my-skill",
                "--is-for-sale",
                "true",
                "--visibility",
                "private",
                "--selling-description-md",
                "Paid summary",
            ]
        )
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        payload = {"skill": {"namespace": "acme", "slug": "my-skill", "visibility": "private"}, "sale": {"is_for_sale": True}}
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()),
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_skills(args)
        self.assertEqual(rc, 0)
        self.assertEqual(mock_client.request.call_args.kwargs["method"], "PATCH")
        self.assertEqual(mock_client.request.call_args.kwargs["path"], "/v1/skills/acme/my-skill/commerce")
        self.assertEqual(
            mock_client.request.call_args.kwargs["json_body"],
            {"is_for_sale": True, "visibility": "private", "selling_description_md": "Paid summary"},
        )

    def test_buy_with_poll_uses_buy_and_invoice_endpoints(self) -> None:
        args = build_parser().parse_args(["skills", "buy", "acme/my-skill", "--poll"])
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        buy_payload = {
            "created": True,
            "invoice": {
                "id": "inv_1",
                "status": "pending",
                "pay_to_address": "UQ...",
                "memo": "memo",
                "amount_ton": "2.34",
                "expires_at": "2026-02-21T10:40:00.000Z",
                "access_granted": False,
            },
        }
        status_payload = {"invoice": {"id": "inv_1", "status": "paid", "access_granted": True}}
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("skilldock.cli.time.sleep"),
            patch("sys.stdout", new=io.StringIO()) as stdout,
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.side_effect = [_FakeResponse(buy_payload), _FakeResponse(status_payload)]
            rc = cmd_skills(args)
        self.assertEqual(rc, 0)
        self.assertEqual(mock_client.request.call_args_list[0].kwargs["path"], "/v1/skills/acme/my-skill/buy")
        self.assertEqual(mock_client.request.call_args_list[0].kwargs["json_body"], {"payment_provider": "ton"})
        self.assertEqual(mock_client.request.call_args_list[1].kwargs["path"], "/v1/skill-purchases/invoices/inv_1")
        self.assertIn("status: paid", stdout.getvalue())

    def test_buy_accepts_referral_and_payment_provider(self) -> None:
        args = build_parser().parse_args(
            ["skills", "buy", "acme/my-skill", "--payment-provider", "ton", "--referral-code", "a"]
        )
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        payload = {"created": True, "invoice": {"id": "inv_1", "status": "pending"}}
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()),
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_skills(args)
        self.assertEqual(rc, 0)
        self.assertEqual(
            mock_client.request.call_args.kwargs["json_body"],
            {"payment_provider": "ton", "referral_code": "a"},
        )

    def test_invoice_calls_invoice_endpoint(self) -> None:
        args = build_parser().parse_args(["skills", "invoice", "inv_1"])
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        payload = {"invoice": {"id": "inv_1", "status": "paid", "access_granted": True}}
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()),
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_skills(args)
        self.assertEqual(rc, 0)
        self.assertEqual(mock_client.request.call_args.kwargs["method"], "GET")
        self.assertEqual(mock_client.request.call_args.kwargs["path"], "/v1/skill-purchases/invoices/inv_1")

    def test_bought_calls_bought_skills_endpoint(self) -> None:
        args = build_parser().parse_args(["skills", "bought", "--page", "1", "--per-page", "20"])
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        payload = {
            "page": 1,
            "per_page": 20,
            "has_more": False,
            "items": [
                {
                    "skill": {"namespace": "acme", "slug": "my-skill", "title": "My Skill"},
                    "purchased_at": "2026-02-27T10:00:00.000Z",
                }
            ],
        }
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()) as stdout,
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_skills(args)
        self.assertEqual(rc, 0)
        self.assertEqual(mock_client.request.call_args.kwargs["method"], "GET")
        self.assertEqual(mock_client.request.call_args.kwargs["path"], "/v1/me/bought-skills")
        self.assertEqual(mock_client.request.call_args.kwargs["params"], {"page": 1, "per_page": 20})
        self.assertIn("acme/my-skill", stdout.getvalue())

    def test_sales_with_skill_calls_skill_sales_endpoint(self) -> None:
        args = build_parser().parse_args(["skills", "sales", "--skill", "acme/my-skill"])
        cfg = Config(
            openapi_url=DEFAULT_OPENAPI_URL,
            base_url="https://api.skilldock.io",
            token="tok_123",
            timeout_s=30.0,
        )
        payload = {"page": 1, "per_page": 20, "has_more": False, "total_sales": 1, "items": []}
        with (
            patch("skilldock.cli.load_config", return_value=cfg),
            patch("skilldock.cli.SkilldockClient") as mock_client_cls,
            patch("sys.stdout", new=io.StringIO()),
        ):
            mock_client = mock_client_cls.return_value
            mock_client.request.return_value = _FakeResponse(payload)
            rc = cmd_skills(args)
        self.assertEqual(rc, 0)
        self.assertEqual(mock_client.request.call_args.kwargs["path"], "/v1/skills/acme/my-skill/sales")
