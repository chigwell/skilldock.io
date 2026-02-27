import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from skilldock.client import SkilldockError
from skilldock.local_skills import (
    ApiReleaseRepository,
    DependencySpec,
    LocalSkillManager,
    SkillRef,
    SkillRelease,
    compare_versions,
    parse_skill_ref,
    resolve_dependency_graph,
    version_satisfies,
)


class FakeRepo:
    def __init__(self, releases: dict[str, list[SkillRelease]]) -> None:
        self._releases = releases

    def list_releases(self, ref: SkillRef) -> list[SkillRelease]:
        return list(self._releases.get(ref.key, []))

    def get_release(self, ref: SkillRef, version: str) -> SkillRelease | None:
        for rel in self._releases.get(ref.key, []):
            if compare_versions(rel.version, version) == 0:
                return rel
        return None

    def download_archive(self, release: SkillRelease) -> bytes:
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("SKILL.md", f"# {release.ref.key}\n")
            zf.writestr("VERSION.txt", release.version + "\n")
        return buf.getvalue()


class ExactOnlyRepo:
    def __init__(self, release: SkillRelease) -> None:
        self._release = release

    def list_releases(self, ref: SkillRef) -> list[SkillRelease]:
        raise SkilldockError("list endpoint unavailable")

    def get_release(self, ref: SkillRef, version: str) -> SkillRelease | None:
        if ref.key == self._release.ref.key and compare_versions(version, self._release.version) == 0:
            return self._release
        return None

    def download_archive(self, release: SkillRelease) -> bytes:
        raise NotImplementedError


class ListHydrationRepo:
    def __init__(
        self,
        *,
        listed: dict[str, list[SkillRelease]],
        by_version: dict[tuple[str, str], SkillRelease] | None = None,
    ) -> None:
        self._listed = listed
        self._by_version = dict(by_version or {})

    def list_releases(self, ref: SkillRef) -> list[SkillRelease]:
        return list(self._listed.get(ref.key, []))

    def get_release(self, ref: SkillRef, version: str) -> SkillRelease | None:
        key = (ref.key, version)
        if key in self._by_version:
            return self._by_version[key]
        for rel in self._listed.get(ref.key, []):
            if compare_versions(rel.version, version) == 0:
                return rel
        return None

    def download_archive(self, release: SkillRelease) -> bytes:
        if not release.download_url:
            raise SkilldockError(f"Release {release.ref.key}@{release.version} has no download URL.")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("SKILL.md", f"# {release.ref.key}\n")
            zf.writestr("VERSION.txt", release.version + "\n")
        return buf.getvalue()


class _JsonResponse:
    def __init__(self, payload):
        self._payload = payload

    def json(self):
        return self._payload


class _BinaryResponse:
    def __init__(self, content: bytes):
        self.content = content


class _CaptureApiClient:
    def __init__(self, *, token: str | None):
        self.token = token
        self.base_url = "https://api.skilldock.io"
        self.calls: list[dict[str, object]] = []

    def request(self, *, method: str, path: str, params=None, auth: bool = True, **kwargs):
        self.calls.append(
            {
                "method": method,
                "path": path,
                "params": params,
                "auth": auth,
                "auth_optional": bool(kwargs.get("auth_optional")),
            }
        )
        if path.endswith("/releases"):
            page = 1
            if isinstance(params, dict) and isinstance(params.get("page"), int):
                page = params["page"]
            if page == 1:
                return _JsonResponse(
                    {
                        "page": 1,
                        "per_page": 100,
                        "has_more": True,
                        "items": [{"version": "1.2.3", "download_url": "/v1/files/file_1/download"}],
                    }
                )
            return _JsonResponse(
                {
                    "page": page,
                    "per_page": 100,
                    "has_more": False,
                    "items": [{"version": "1.2.2", "download_url": "/v1/files/file_1/download"}],
                }
            )
        if path == "/v1/files/file_1/download":
            return _BinaryResponse(b"zip-bytes")
        if path == "https://cdn.example.com/file.zip":
            return _BinaryResponse(b"zip-bytes")
        raise AssertionError(f"unexpected path: {path}")


def _dep(skill: str, *, req: str | None = None, release_version: str | None = None) -> DependencySpec:
    return DependencySpec(ref=parse_skill_ref(skill), version_requirement=req, release_version=release_version)


def _release(
    skill: str,
    version: str,
    deps: tuple[DependencySpec, ...] = (),
    download_url: str | None = "https://example.invalid/archive.zip",
) -> SkillRelease:
    return SkillRelease(ref=parse_skill_ref(skill), version=version, dependencies=deps, download_url=download_url)


class TestVersionSpec(unittest.TestCase):
    def test_version_satisfies_common_specifiers(self) -> None:
        self.assertTrue(version_satisfies("1.2.3", "1.2.3"))
        self.assertTrue(version_satisfies("1.2.3", ">=1.0.0 <2.0.0"))
        self.assertTrue(version_satisfies("1.2.3", "^1.1.0"))
        self.assertTrue(version_satisfies("1.2.3", "~1.2.0"))
        self.assertTrue(version_satisfies("3.1.4", "latest"))
        self.assertFalse(version_satisfies("2.0.0", "<2.0.0"))
        self.assertFalse(version_satisfies("1.2.3", "^2.0.0"))


class TestResolver(unittest.TestCase):
    def test_resolver_backtracks_for_compatible_graph(self) -> None:
        repo = FakeRepo(
            {
                "acme/app": [
                    _release("acme/app", "2.0.0", (_dep("core/runtime", req="^2.0.0"),)),
                    _release("acme/app", "1.0.0", (_dep("core/runtime", req="^1.0.0"),)),
                ],
                "tools/helper": [
                    _release("tools/helper", "1.0.0", (_dep("core/runtime", req="^1.0.0"),)),
                ],
                "core/runtime": [
                    _release("core/runtime", "2.0.0"),
                    _release("core/runtime", "1.5.0"),
                ],
            }
        )

        resolved, _ = resolve_dependency_graph(
            direct_requirements={"acme/app": "latest", "tools/helper": "latest"},
            repo=repo,
        )

        self.assertEqual(resolved["acme/app"].version, "1.0.0")
        self.assertEqual(resolved["core/runtime"].version, "1.5.0")

    def test_resolver_raises_on_conflict(self) -> None:
        repo = FakeRepo(
            {
                "acme/app": [
                    _release("acme/app", "2.0.0", (_dep("core/runtime", req="^2.0.0"),)),
                ],
                "tools/helper": [
                    _release("tools/helper", "1.0.0", (_dep("core/runtime", req="^1.0.0"),)),
                ],
                "core/runtime": [
                    _release("core/runtime", "2.0.0"),
                ],
            }
        )

        with self.assertRaises(SkilldockError):
            resolve_dependency_graph(
                direct_requirements={"acme/app": "latest", "tools/helper": "latest"},
                repo=repo,
            )

    def test_resolver_exact_version_without_list_endpoint(self) -> None:
        rel = _release("chigwel/my-skill", "1.2.4")
        repo = ExactOnlyRepo(rel)

        resolved, _ = resolve_dependency_graph(
            direct_requirements={"chigwel/my-skill": "1.2.4"},
            repo=repo,
        )

        self.assertEqual(resolved["chigwel/my-skill"].version, "1.2.4")

    def test_resolver_hydrates_list_release_without_download_url(self) -> None:
        ref = parse_skill_ref("acme/tool")
        listed = _release("acme/tool", "1.0.0", download_url=None)
        hydrated = _release("acme/tool", "1.0.0", download_url="/v1/files/tool_100/download")
        repo = ListHydrationRepo(listed={ref.key: [listed]}, by_version={(ref.key, "1.0.0"): hydrated})

        resolved, _ = resolve_dependency_graph(direct_requirements={ref.key: "latest"}, repo=repo)

        self.assertEqual(resolved[ref.key].version, "1.0.0")
        self.assertEqual(resolved[ref.key].download_url, "/v1/files/tool_100/download")

    def test_resolver_fails_when_hydrated_release_has_no_download_url(self) -> None:
        ref = parse_skill_ref("acme/tool")
        listed = _release("acme/tool", "1.0.0", download_url=None)
        repo = ListHydrationRepo(listed={ref.key: [listed]}, by_version={(ref.key, "1.0.0"): listed})

        with self.assertRaises(SkilldockError) as ctx:
            resolve_dependency_graph(direct_requirements={ref.key: "latest"}, repo=repo)

        self.assertIn("List payload had no download_url", str(ctx.exception))
        self.assertIn("attempted per-version lookup", str(ctx.exception))


class TestLocalManager(unittest.TestCase):
    def test_install_update_uninstall_reconcile(self) -> None:
        repo = FakeRepo(
            {
                "acme/app": [
                    _release("acme/app", "2.0.0", (_dep("core/runtime", release_version="2.0.0"),)),
                    _release("acme/app", "1.0.0", (_dep("core/runtime", release_version="1.0.0"),)),
                ],
                "core/runtime": [
                    _release("core/runtime", "2.0.0"),
                    _release("core/runtime", "1.0.0"),
                ],
            }
        )

        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            manager = LocalSkillManager(skills_dir=skills_dir, repo=repo)

            first = manager.install(skill="acme/app", requirement="1.0.0")
            self.assertIn("acme/app", first.installed)
            self.assertIn("core/runtime", first.installed)
            self.assertTrue((skills_dir / "acme" / "app" / "SKILL.md").exists())
            self.assertTrue((skills_dir / "core" / "runtime" / "SKILL.md").exists())

            second = manager.install(skill="acme/app", requirement="1.0.0")
            self.assertIn("acme/app", second.unchanged)
            self.assertIn("core/runtime", second.unchanged)

            third = manager.install(skill="acme/app", requirement="2.0.0")
            self.assertIn("acme/app", third.updated)
            self.assertIn("core/runtime", third.updated)

            fourth = manager.uninstall(skill="acme/app")
            self.assertIn("acme/app", fourth.removed)
            self.assertIn("core/runtime", fourth.removed)
            self.assertFalse((skills_dir / "acme" / "app").exists())
            self.assertFalse((skills_dir / "core" / "runtime").exists())
            self.assertTrue((Path(td) / ".skilldock.json").exists())
            self.assertTrue((Path(td) / ".skilldock.lock.json").exists())

    def test_install_skips_missing_direct_skill_with_warning(self) -> None:
        repo = FakeRepo(
            {
                "acme/app": [
                    _release("acme/app", "1.0.0"),
                ],
            }
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills_dir = root / "skills"
            manager = LocalSkillManager(skills_dir=skills_dir, repo=repo)
            (root / ".skilldock.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills_dir": "skills",
                        "direct": {
                            "chigwel/my-skill": "1.2.4",
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = manager.install(skill="acme/app", requirement="1.0.0")

            self.assertIn("acme/app", result.installed)
            self.assertTrue(any(w.startswith("Skipping missing direct skill: chigwel/my-skill") for w in result.warnings))
            self.assertTrue(any("reason:" in w for w in result.warnings))
            manifest = json.loads((root / ".skilldock.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest.get("direct"), {"acme/app": "1.0.0"})

    def test_install_skips_unresolvable_direct_skill_without_download_url(self) -> None:
        repo = FakeRepo(
            {
                "acme/app": [
                    _release("acme/app", "1.0.0"),
                ],
                "chigwel/chrome-mcp-client": [
                    _release("chigwel/chrome-mcp-client", "0.1.0", download_url=None),
                ],
            }
        )

        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            skills_dir = root / "skills"
            manager = LocalSkillManager(skills_dir=skills_dir, repo=repo)
            (root / ".skilldock.json").write_text(
                json.dumps(
                    {
                        "schema_version": 1,
                        "skills_dir": "skills",
                        "direct": {
                            "chigwel/chrome-mcp-client": "0.1.0",
                        },
                    }
                ),
                encoding="utf-8",
            )

            result = manager.install(skill="acme/app", requirement="1.0.0")

            self.assertIn("acme/app", result.installed)
            self.assertTrue(
                any(w.startswith("Skipping unresolved direct skill: chigwel/chrome-mcp-client") for w in result.warnings)
            )
            manifest = json.loads((root / ".skilldock.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest.get("direct"), {"acme/app": "1.0.0"})

    def test_install_hydrates_dependency_download_url_from_get_release(self) -> None:
        listed_a = _release("acme/app", "1.0.0", (_dep("core/runtime", req=">=0.1.0"),))
        listed_b = _release("core/runtime", "0.2.0", download_url=None)
        hydrated_b = _release("core/runtime", "0.2.0", download_url="/v1/files/runtime_020/download")
        repo = ListHydrationRepo(
            listed={
                "acme/app": [listed_a],
                "core/runtime": [listed_b],
            },
            by_version={
                ("core/runtime", "0.2.0"): hydrated_b,
            },
        )

        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            manager = LocalSkillManager(skills_dir=skills_dir, repo=repo)

            result = manager.install(skill="acme/app", requirement="1.0.0")

            self.assertIn("acme/app", result.installed)
            self.assertIn("core/runtime", result.installed)
            self.assertTrue((skills_dir / "core" / "runtime" / "SKILL.md").exists())

    def test_install_accepts_version_shorthand_in_skill_argument(self) -> None:
        repo = FakeRepo(
            {
                "acme/app": [
                    _release("acme/app", "1.0.0"),
                ],
            }
        )

        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            manager = LocalSkillManager(skills_dir=skills_dir, repo=repo)

            result = manager.install(skill="acme/app@1.0.0", requirement=None)

            self.assertIn("acme/app", result.installed)

    def test_install_rejects_both_shorthand_and_requirement(self) -> None:
        repo = FakeRepo({"acme/app": [_release("acme/app", "1.0.0")]})

        with tempfile.TemporaryDirectory() as td:
            skills_dir = Path(td) / "skills"
            manager = LocalSkillManager(skills_dir=skills_dir, repo=repo)

            with self.assertRaises(SkilldockError):
                manager.install(skill="acme/app@1.0.0", requirement="2.0.0")


class TestApiReleaseRepositoryAuth(unittest.TestCase):
    def test_list_releases_uses_auth_when_token_present(self) -> None:
        client = _CaptureApiClient(token="tok_123")
        repo = ApiReleaseRepository(client)  # type: ignore[arg-type]
        ref = parse_skill_ref("acme/my-skill")

        repo.list_releases(ref)

        self.assertTrue(client.calls[0]["auth"])
        self.assertTrue(client.calls[0]["auth_optional"])
        self.assertEqual(client.calls[0]["params"], {"page": 1, "per_page": 100})
        self.assertEqual(client.calls[1]["params"], {"page": 2, "per_page": 100})
        self.assertTrue(client.calls[1]["auth_optional"])

    def test_list_releases_uses_anonymous_when_token_missing(self) -> None:
        client = _CaptureApiClient(token=None)
        repo = ApiReleaseRepository(client)  # type: ignore[arg-type]
        ref = parse_skill_ref("acme/my-skill")

        repo.list_releases(ref)

        self.assertFalse(client.calls[0]["auth"])
        self.assertTrue(client.calls[0]["auth_optional"])

    def test_download_archive_sends_auth_for_internal_file_url(self) -> None:
        client = _CaptureApiClient(token="tok_123")
        repo = ApiReleaseRepository(client)  # type: ignore[arg-type]
        release = SkillRelease(
            ref=parse_skill_ref("acme/my-skill"),
            version="1.2.3",
            dependencies=(),
            download_url="/v1/files/file_1/download",
        )

        data = repo.download_archive(release)

        self.assertEqual(data, b"zip-bytes")
        self.assertTrue(client.calls[-1]["auth"])
        self.assertTrue(client.calls[-1]["auth_optional"])

    def test_download_archive_does_not_send_auth_to_external_host(self) -> None:
        client = _CaptureApiClient(token="tok_123")
        repo = ApiReleaseRepository(client)  # type: ignore[arg-type]
        release = SkillRelease(
            ref=parse_skill_ref("acme/my-skill"),
            version="1.2.3",
            dependencies=(),
            download_url="https://cdn.example.com/file.zip",
        )

        data = repo.download_archive(release)

        self.assertEqual(data, b"zip-bytes")
        self.assertFalse(client.calls[-1]["auth"])
        self.assertTrue(client.calls[-1]["auth_optional"])
