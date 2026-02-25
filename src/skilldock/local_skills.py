from __future__ import annotations

import copy
import io
import json
import os
import re
import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import cmp_to_key
from pathlib import Path
from typing import Any, Protocol
from urllib.parse import quote, urlsplit, urlunsplit

from .client import SkilldockClient, SkilldockError, SkilldockHTTPError

MANIFEST_FILENAME = ".skilldock.json"
LOCK_FILENAME = ".skilldock.lock.json"
INSTALL_META_FILENAME = ".skilldock-meta.json"


@dataclass(frozen=True)
class SkillRef:
    namespace: str
    slug: str

    @property
    def key(self) -> str:
        return f"{self.namespace}/{self.slug}"


@dataclass(frozen=True)
class DependencySpec:
    ref: SkillRef
    version_requirement: str | None = None
    release_version: str | None = None


@dataclass(frozen=True)
class SkillRelease:
    ref: SkillRef
    version: str
    dependencies: tuple[DependencySpec, ...]
    sha256: str | None = None
    download_url: str | None = None


@dataclass(frozen=True)
class Requirement:
    specifier: str
    source: str


@dataclass(frozen=True)
class ReconcileResult:
    installed: tuple[str, ...]
    updated: tuple[str, ...]
    removed: tuple[str, ...]
    unchanged: tuple[str, ...]
    warnings: tuple[str, ...]
    manifest_path: Path
    lock_path: Path


class ReleaseRepository(Protocol):
    def list_releases(self, ref: SkillRef) -> list[SkillRelease]:
        ...

    def get_release(self, ref: SkillRef, version: str) -> SkillRelease | None:
        ...

    def download_archive(self, release: SkillRelease) -> bytes:
        ...


def parse_skill_ref(value: str) -> SkillRef:
    raw = value.strip()
    if "/" not in raw:
        raise SkilldockError(f"Invalid skill identifier {value!r}. Expected <namespace>/<slug>.")
    namespace, slug = raw.split("/", 1)
    namespace = namespace.strip()
    slug = slug.strip()
    if not namespace or not slug:
        raise SkilldockError(f"Invalid skill identifier {value!r}. Expected <namespace>/<slug>.")
    return SkillRef(namespace=namespace, slug=slug)


def _split_install_skill_and_requirement(skill: str, requirement: str | None) -> tuple[str, str | None]:
    skill_value = skill.strip()
    if not skill_value:
        raise SkilldockError("Invalid skill identifier ''. Expected <namespace>/<slug>.")

    at_idx = skill_value.rfind("@")
    if at_idx > 0:
        shorthand_skill = skill_value[:at_idx].strip()
        shorthand_req = skill_value[at_idx + 1 :].strip()
        if "/" in shorthand_skill and shorthand_req:
            if requirement:
                raise SkilldockError("Specify version either as @<version> or --version, not both.")
            return shorthand_skill, shorthand_req

    return skill_value, requirement


def normalize_requirement(value: str | None) -> str:
    raw = (value or "").strip()
    return raw if raw else "latest"


def _split_version(version: str) -> tuple[tuple[int, ...], tuple[str, ...] | None]:
    if not isinstance(version, str):
        raise ValueError("version must be str")
    raw = version.strip()
    if not raw:
        raise ValueError("empty version")
    raw = raw.split("+", 1)[0]  # ignore build metadata
    if "-" in raw:
        main_s, pre_s = raw.split("-", 1)
        pre_parts = tuple(p for p in pre_s.split(".") if p != "")
    else:
        main_s = raw
        pre_parts = None
    main_parts = main_s.split(".")
    if any(not p.isdigit() for p in main_parts):
        raise ValueError(f"Unsupported version format: {version!r}")
    nums = [int(p) for p in main_parts]
    while len(nums) < 3:
        nums.append(0)
    return tuple(nums), pre_parts


def compare_versions(a: str, b: str) -> int:
    try:
        ma, pa = _split_version(a)
        mb, pb = _split_version(b)
    except ValueError:
        if a < b:
            return -1
        if a > b:
            return 1
        return 0
    if ma < mb:
        return -1
    if ma > mb:
        return 1

    if pa is None and pb is None:
        return 0
    if pa is None:
        return 1
    if pb is None:
        return -1

    for i in range(max(len(pa), len(pb))):
        if i >= len(pa):
            return -1
        if i >= len(pb):
            return 1
        x = pa[i]
        y = pb[i]
        x_num = x.isdigit()
        y_num = y.isdigit()
        if x_num and y_num:
            xi = int(x)
            yi = int(y)
            if xi < yi:
                return -1
            if xi > yi:
                return 1
            continue
        if x_num and not y_num:
            return -1
        if not x_num and y_num:
            return 1
        if x < y:
            return -1
        if x > y:
            return 1
    return 0


def _expand_caret(spec: str) -> list[str]:
    base = spec[1:].strip()
    major, minor, patch = _split_version(base)[0][:3]
    lower = f">={major}.{minor}.{patch}"
    if major > 0:
        upper = f"<{major + 1}.0.0"
    elif minor > 0:
        upper = f"<0.{minor + 1}.0"
    else:
        upper = f"<0.0.{patch + 1}"
    return [lower, upper]


def _expand_tilde(spec: str) -> list[str]:
    base = spec[1:].strip()
    major, minor, patch = _split_version(base)[0][:3]
    lower = f">={major}.{minor}.{patch}"
    upper = f"<{major}.{minor + 1}.0"
    return [lower, upper]


def _split_specifier(specifier: str) -> list[str]:
    s = specifier.strip()
    if not s:
        return ["latest"]
    s = s.replace(",", " ")
    tokens = [t for t in s.split() if t]
    if not tokens:
        return ["latest"]
    out: list[str] = []
    for token in tokens:
        if token.startswith("^"):
            try:
                out.extend(_expand_caret(token))
            except ValueError as e:
                raise SkilldockError(f"Invalid version requirement: {token!r}") from e
            continue
        if token.startswith("~"):
            try:
                out.extend(_expand_tilde(token))
            except ValueError as e:
                raise SkilldockError(f"Invalid version requirement: {token!r}") from e
            continue
        out.append(token)
    return out


_COMPARATOR_RE = re.compile(r"^(>=|<=|>|<|==|=)?\s*([0-9A-Za-z][0-9A-Za-z.\-+]*)$")
_MISSING_DOWNLOAD_URL_RE = re.compile(r"Release\s+([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)@([^\s]+)\s+has no download URL\.?")


def version_satisfies(version: str, specifier: str) -> bool:
    for token in _split_specifier(specifier):
        t = token.strip().lower()
        if t in ("latest", "*"):
            continue

        m = _COMPARATOR_RE.match(token.strip())
        if not m:
            return False

        op = m.group(1) or "="
        rhs = m.group(2)
        cmp = compare_versions(version, rhs)

        if op in ("=", "=="):
            if cmp != 0:
                return False
            continue
        if op == ">":
            if cmp <= 0:
                return False
            continue
        if op == ">=":
            if cmp < 0:
                return False
            continue
        if op == "<":
            if cmp >= 0:
                return False
            continue
        if op == "<=":
            if cmp > 0:
                return False
            continue
        return False
    return True


def _extract_exact_version(specifier: str) -> str | None:
    tokens = _split_specifier(specifier)
    if len(tokens) != 1:
        return None
    token = tokens[0].strip()
    if not token or token.lower() in ("latest", "*"):
        return None
    if token.startswith(("^", "~", ">", "<")):
        return None

    m = _COMPARATOR_RE.match(token)
    if not m:
        return None
    op = m.group(1) or "="
    rhs = m.group(2)
    if op in ("=", "=="):
        return rhs
    return None


def _version_satisfies_all(version: str, requirements: list[Requirement]) -> bool:
    return all(version_satisfies(version, r.specifier) for r in requirements)


def _format_requirement_debug(requirements: list[Requirement]) -> str:
    parts = [f"{r.specifier} (from {r.source})" for r in requirements]
    return ", ".join(parts) if parts else "<none>"


def _has_download_url(release: SkillRelease) -> bool:
    return bool(isinstance(release.download_url, str) and release.download_url.strip())


def _parse_missing_download_url_error(message: str) -> tuple[str, str] | None:
    m = _MISSING_DOWNLOAD_URL_RE.search(message)
    if not m:
        return None
    return m.group(1), m.group(2)


def _hydrate_release_from_version_lookup(release: SkillRelease, *, repo: ReleaseRepository) -> SkillRelease:
    if _has_download_url(release):
        return release
    hydrated = repo.get_release(release.ref, release.version)
    if hydrated is None:
        return release
    if hydrated.ref.key != release.ref.key:
        return release
    if compare_versions(hydrated.version, release.version) != 0:
        return release
    return hydrated


def _is_release_unavailable_error(message: str) -> bool:
    if "Skill not found or not visible:" in message:
        return True
    if "No release found for " in message:
        return True
    if "No downloadable release found for " in message:
        return True
    return _parse_missing_download_url_error(message) is not None


def _candidate_releases(ref: SkillRef, requirements: list[Requirement], repo: ReleaseRepository) -> list[SkillRelease]:
    exact_versions = {v for r in requirements if (v := _extract_exact_version(r.specifier)) is not None}
    if len(exact_versions) > 1:
        conflict = ", ".join(sorted(exact_versions))
        raise SkilldockError(
            f"Dependency conflict for {ref.key}: multiple exact versions requested ({conflict}). "
            f"Constraints: {_format_requirement_debug(requirements)}"
        )

    # Fast path: if constraints collapse to one exact version, prefer direct lookup.
    # Some APIs expose GET /releases/{version} but not list endpoints.
    if len(exact_versions) == 1:
        version = next(iter(exact_versions))
        rel = repo.get_release(ref, version)
        if rel and _version_satisfies_all(rel.version, requirements) and _has_download_url(rel):
            return [rel]

    releases = repo.list_releases(ref)
    releases = sorted(
        releases,
        key=cmp_to_key(lambda a, b: compare_versions(a.version, b.version)),
        reverse=True,
    )
    matched = [r for r in releases if _version_satisfies_all(r.version, requirements)]
    hydrated = [_hydrate_release_from_version_lookup(r, repo=repo) for r in matched]
    filtered = [r for r in hydrated if _has_download_url(r)]
    if filtered:
        return filtered

    if matched:
        versions = ", ".join(sorted(dict.fromkeys(r.version for r in matched), key=cmp_to_key(compare_versions), reverse=True))
        raise SkilldockError(
            f"No downloadable release found for {ref.key} that satisfies constraints: "
            f"{_format_requirement_debug(requirements)}. List payload had no download_url; "
            f"attempted per-version lookup for {versions}, but none provided a download URL."
        )

    raise SkilldockError(
        f"No release found for {ref.key} that satisfies constraints: {_format_requirement_debug(requirements)}"
    )


def resolve_dependency_graph(
    *,
    direct_requirements: dict[str, str],
    repo: ReleaseRepository,
) -> tuple[dict[str, SkillRelease], dict[str, list[Requirement]]]:
    constraints: dict[str, list[Requirement]] = {}
    pending: list[str] = []
    last_error: SkilldockError | None = None

    for key, spec in sorted(direct_requirements.items()):
        ref = parse_skill_ref(key)
        constraints.setdefault(ref.key, []).append(Requirement(specifier=normalize_requirement(spec), source="direct"))
        if ref.key not in pending:
            pending.append(ref.key)

    def _search(
        *,
        selected: dict[str, SkillRelease],
        constraints_map: dict[str, list[Requirement]],
        pending_keys: list[str],
    ) -> tuple[dict[str, SkillRelease], dict[str, list[Requirement]]] | None:
        selected_mut = dict(selected)
        pending_mut = list(dict.fromkeys(pending_keys))

        # If constraints changed for already-selected nodes, revisit those nodes.
        for key in list(selected_mut.keys()):
            reqs = constraints_map.get(key, [])
            if _version_satisfies_all(selected_mut[key].version, reqs):
                continue
            selected_mut.pop(key)
            if key not in pending_mut:
                pending_mut.insert(0, key)

        if not pending_mut:
            return selected_mut, constraints_map

        key = pending_mut[0]
        rest = pending_mut[1:]
        ref = parse_skill_ref(key)
        reqs = constraints_map.get(key, [])

        nonlocal last_error
        try:
            candidates = _candidate_releases(ref, reqs, repo)
        except SkilldockError as e:
            last_error = e
            return None
        for candidate in candidates:
            selected_next = dict(selected_mut)
            selected_next[key] = candidate
            constraints_next = copy.deepcopy(constraints_map)
            pending_next = list(rest)

            for dep in candidate.dependencies:
                dep_key = dep.ref.key
                dep_specs: list[str] = []
                if dep.release_version:
                    dep_specs.append(f"={dep.release_version}")
                if dep.version_requirement:
                    dep_specs.append(dep.version_requirement)
                if not dep_specs:
                    dep_specs.append("latest")

                for dep_spec in dep_specs:
                    constraints_next.setdefault(dep_key, []).append(
                        Requirement(specifier=dep_spec, source=f"{key}@{candidate.version}")
                    )

                if dep_key in selected_next and not _version_satisfies_all(
                    selected_next[dep_key].version, constraints_next[dep_key]
                ):
                    selected_next.pop(dep_key)
                if dep_key not in selected_next and dep_key not in pending_next:
                    pending_next.append(dep_key)

            solved = _search(selected=selected_next, constraints_map=constraints_next, pending_keys=pending_next)
            if solved is not None:
                return solved
        return None

    solved = _search(selected={}, constraints_map=constraints, pending_keys=pending)
    if solved is None:
        if last_error:
            raise SkilldockError(f"Could not resolve dependency graph. Last error: {last_error}") from last_error
        raise SkilldockError("Could not resolve dependency graph.")
    return solved


def _origin(url: str) -> str | None:
    try:
        parts = urlsplit(url)
    except Exception:
        return None
    if not parts.scheme or not parts.netloc:
        return None
    return urlunsplit((parts.scheme, parts.netloc, "", "", "")).rstrip("/")


def _unwrap_success_envelope(obj: Any) -> Any:
    if not isinstance(obj, dict):
        return obj
    if obj.get("success") is True and "data" in obj:
        return obj["data"]
    if obj.get("success") is False and "error" in obj:
        raise SkilldockError(f"API error: {obj.get('error')}")
    return obj


def _parse_dependency_entry(raw: Any) -> DependencySpec | None:
    if isinstance(raw, str):
        spec = raw.strip()
        if not spec:
            return None
        if "@" in spec:
            skill_s, req = spec.split("@", 1)
            ref = parse_skill_ref(skill_s)
            req = req.strip() or None
            return DependencySpec(ref=ref, version_requirement=req, release_version=None)
        ref = parse_skill_ref(spec)
        return DependencySpec(ref=ref)

    if not isinstance(raw, dict):
        return None

    if isinstance(raw.get("namespace"), str) and isinstance(raw.get("slug"), str):
        ref = SkillRef(namespace=raw["namespace"].strip(), slug=raw["slug"].strip())
    elif isinstance(raw.get("skill"), str):
        ref = parse_skill_ref(raw["skill"])
    else:
        return None

    vr = raw.get("version_requirement")
    rv = raw.get("release_version")
    version_requirement = vr.strip() if isinstance(vr, str) and vr.strip() else None
    release_version = rv.strip() if isinstance(rv, str) and rv.strip() else None
    return DependencySpec(ref=ref, version_requirement=version_requirement, release_version=release_version)


def _extract_items(obj: Any) -> list[Any]:
    if isinstance(obj, list):
        return obj
    if isinstance(obj, dict):
        for key in ("items", "releases", "data"):
            value = obj.get(key)
            if isinstance(value, list):
                return value
        if isinstance(obj.get("release"), dict):
            return [obj["release"]]
        return [obj]
    return []


def _parse_release_obj(obj: Any, *, ref: SkillRef) -> SkillRelease | None:
    if not isinstance(obj, dict):
        return None

    data = obj.get("release") if isinstance(obj.get("release"), dict) else obj
    if not isinstance(data, dict):
        return None

    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        return None
    version = version.strip()

    deps_raw = data.get("dependencies")
    deps: list[DependencySpec] = []
    if isinstance(deps_raw, list):
        for dep_raw in deps_raw:
            dep = _parse_dependency_entry(dep_raw)
            if dep is not None:
                deps.append(dep)

    sha256: str | None = None
    download_url: str | None = None

    files = data.get("files")
    file_items = files if isinstance(files, list) else []
    preferred_kinds = {"archive", "source", "zip"}
    chosen: dict[str, Any] | None = None

    for f in file_items:
        if not isinstance(f, dict):
            continue
        if not isinstance(f.get("download_url"), str):
            continue
        kind = str(f.get("kind", "")).strip().lower()
        if kind in preferred_kinds:
            chosen = f
            break
        if chosen is None:
            chosen = f

    if chosen is not None:
        if isinstance(chosen.get("download_url"), str):
            val = chosen["download_url"].strip()
            if val:
                download_url = val
        if isinstance(chosen.get("sha256"), str):
            val = chosen["sha256"].strip()
            if val:
                sha256 = val

    if download_url is None:
        if isinstance(data.get("download_url"), str):
            val = data["download_url"].strip()
            if val:
                download_url = val
    if sha256 is None:
        if isinstance(data.get("sha256"), str):
            val = data["sha256"].strip()
            if val:
                sha256 = val

    return SkillRelease(ref=ref, version=version, dependencies=tuple(deps), sha256=sha256, download_url=download_url)


class ApiReleaseRepository:
    def __init__(self, client: SkilldockClient) -> None:
        self._client = client
        self._list_cache: dict[str, list[SkillRelease]] = {}
        self._release_cache: dict[tuple[str, str], SkillRelease | None] = {}

    def _auth_for_url(self, url: str) -> bool:
        if not self._client.token:
            return False
        if url.startswith("/"):
            return True
        url_origin = _origin(url)
        base_origin = _origin(self._client.base_url)
        return bool(url_origin and base_origin and url_origin == base_origin)

    def _get_json(self, *, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = self._client.request(
            method="GET",
            path=path,
            params=params,
            auth=self._auth_for_url(path),
        )
        return _unwrap_success_envelope(resp.json())

    def list_releases(self, ref: SkillRef) -> list[SkillRelease]:
        if ref.key in self._list_cache:
            return list(self._list_cache[ref.key])

        path = f"/v1/skills/{quote(ref.namespace, safe='')}/{quote(ref.slug, safe='')}/releases"
        try:
            page = 1
            data: Any = {}
            items: list[Any] = []
            while True:
                data = self._get_json(path=path, params={"page": page, "per_page": 100})
                page_items = _extract_items(data)
                items.extend(page_items)
                if not (isinstance(data, dict) and bool(data.get("has_more"))):
                    break
                page += 1
        except SkilldockHTTPError as e:
            if e.status_code != 404:
                raise
            raise SkilldockError(f"Skill not found or not visible: {ref.key}") from e

        releases: list[SkillRelease] = []
        seen: set[str] = set()
        for item in items:
            rel = _parse_release_obj(item, ref=ref)
            if rel is None:
                continue
            if rel.version in seen:
                continue
            seen.add(rel.version)
            releases.append(rel)
            self._release_cache[(ref.key, rel.version)] = rel

        releases.sort(key=cmp_to_key(lambda a, b: compare_versions(a.version, b.version)), reverse=True)
        self._list_cache[ref.key] = list(releases)
        return releases

    def get_release(self, ref: SkillRef, version: str) -> SkillRelease | None:
        cache_key = (ref.key, version)
        if cache_key in self._release_cache:
            return self._release_cache[cache_key]

        path = f"/v1/skills/{quote(ref.namespace, safe='')}/{quote(ref.slug, safe='')}/releases/{quote(version, safe='')}"
        try:
            data = self._get_json(path=path)
        except SkilldockHTTPError as e:
            if e.status_code == 404:
                # Fallback for APIs that support list but not single-version GET
                for rel in self.list_releases(ref):
                    if compare_versions(rel.version, version) == 0:
                        self._release_cache[cache_key] = rel
                        return rel
                self._release_cache[cache_key] = None
                return None
            raise
        rel = _parse_release_obj(data, ref=ref)
        self._release_cache[cache_key] = rel
        return rel

    def download_archive(self, release: SkillRelease) -> bytes:
        download_url = release.download_url
        if not download_url:
            refreshed = self.get_release(release.ref, release.version)
            if refreshed and refreshed.download_url:
                download_url = refreshed.download_url
        if not download_url:
            raise SkilldockError(f"Release {release.ref.key}@{release.version} has no download URL.")

        resp = self._client.request(method="GET", path=download_url, auth=self._auth_for_url(download_url))
        return resp.content


def _write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    tmp.replace(path)


def _relative_or_abs(path: Path, *, base: Path) -> str:
    try:
        rel = path.relative_to(base)
    except ValueError:
        return str(path)
    return str(rel) if str(rel) else "."


def _safe_extract_zip(zip_bytes: bytes, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(zip_bytes), "r") as zf:
        for info in zf.infolist():
            name = info.filename
            if not name:
                continue
            if name.startswith("/"):
                raise SkilldockError(f"Archive contains an absolute path entry: {name!r}")
            target = (dest / name).resolve()
            base = dest.resolve()
            if not str(target).startswith(str(base) + os.sep) and target != base:
                raise SkilldockError(f"Archive contains an invalid path entry: {name!r}")

            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
                continue

            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info, "r") as src, target.open("wb") as out:
                shutil.copyfileobj(src, out)


class LocalSkillManager:
    def __init__(self, *, skills_dir: Path, repo: ReleaseRepository) -> None:
        self.skills_dir = skills_dir.expanduser().resolve()
        self.root_dir = self.skills_dir.parent
        self.repo = repo
        self.manifest_path = self.root_dir / MANIFEST_FILENAME
        self.lock_path = self.root_dir / LOCK_FILENAME

    def install(self, *, skill: str, requirement: str | None) -> ReconcileResult:
        skill_value, requirement_value = _split_install_skill_and_requirement(skill, requirement)
        ref = parse_skill_ref(skill_value)
        manifest = self._load_manifest()
        direct = dict(manifest.get("direct", {}))
        direct[ref.key] = normalize_requirement(requirement_value)
        return self._reconcile(direct_requirements=direct)

    def uninstall(self, *, skill: str) -> ReconcileResult:
        ref = parse_skill_ref(skill)
        manifest = self._load_manifest()
        direct = dict(manifest.get("direct", {}))
        direct.pop(ref.key, None)
        return self._reconcile(direct_requirements=direct)

    def _ensure_skills_dir(self) -> None:
        try:
            self.skills_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise SkilldockError(f"Could not create skills directory: {self.skills_dir}") from e
        if not self.skills_dir.is_dir():
            raise SkilldockError(f"Skills path is not a directory: {self.skills_dir}")

    def _load_manifest(self) -> dict[str, Any]:
        if not self.manifest_path.exists():
            return {"schema_version": 1, "skills_dir": _relative_or_abs(self.skills_dir, base=self.root_dir), "direct": {}}
        raw = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"schema_version": 1, "skills_dir": _relative_or_abs(self.skills_dir, base=self.root_dir), "direct": {}}
        direct = raw.get("direct")
        if not isinstance(direct, dict):
            direct = {}
        filtered_direct: dict[str, str] = {}
        for key, value in direct.items():
            if not isinstance(key, str):
                continue
            if not isinstance(value, str):
                continue
            filtered_direct[key] = value
        return {
            "schema_version": 1,
            "skills_dir": _relative_or_abs(self.skills_dir, base=self.root_dir),
            "direct": filtered_direct,
        }

    def _save_manifest(self, direct_requirements: dict[str, str]) -> None:
        payload = {
            "schema_version": 1,
            "skills_dir": _relative_or_abs(self.skills_dir, base=self.root_dir),
            "direct": {k: direct_requirements[k] for k in sorted(direct_requirements)},
        }
        _write_json_atomic(self.manifest_path, payload)

    def _load_lock(self) -> dict[str, Any]:
        if not self.lock_path.exists():
            return {"schema_version": 1, "skills": {}}
        raw = json.loads(self.lock_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"schema_version": 1, "skills": {}}
        skills = raw.get("skills")
        if not isinstance(skills, dict):
            skills = {}
        return {"schema_version": 1, "skills": skills}

    def _save_lock(self, resolved: dict[str, SkillRelease]) -> None:
        skills_payload: dict[str, Any] = {}
        for key in sorted(resolved):
            rel = resolved[key]
            deps: list[dict[str, Any]] = []
            for dep in sorted(rel.dependencies, key=lambda d: d.ref.key):
                dep_obj: dict[str, Any] = {"namespace": dep.ref.namespace, "slug": dep.ref.slug}
                if dep.version_requirement:
                    dep_obj["version_requirement"] = dep.version_requirement
                if dep.release_version:
                    dep_obj["release_version"] = dep.release_version
                deps.append(dep_obj)

            item: dict[str, Any] = {
                "namespace": rel.ref.namespace,
                "slug": rel.ref.slug,
                "version": rel.version,
                "dependencies": deps,
            }
            if rel.sha256:
                item["sha256"] = rel.sha256
            if rel.download_url:
                item["download_url"] = rel.download_url
            skills_payload[key] = item

        payload = {
            "schema_version": 1,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "skills": skills_payload,
        }
        _write_json_atomic(self.lock_path, payload)

    def _skill_dir(self, ref: SkillRef) -> Path:
        return self.skills_dir / ref.namespace / ref.slug

    def _read_installed_meta(self, skill_dir: Path) -> dict[str, Any] | None:
        meta_path = skill_dir / INSTALL_META_FILENAME
        if not meta_path.exists():
            return None
        try:
            data = json.loads(meta_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(data, dict):
            return None
        return data

    def _write_installed_meta(self, skill_dir: Path, rel: SkillRelease) -> None:
        meta = {
            "namespace": rel.ref.namespace,
            "slug": rel.ref.slug,
            "version": rel.version,
            "sha256": rel.sha256,
            "installed_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        _write_json_atomic(skill_dir / INSTALL_META_FILENAME, meta)

    def _install_archive(self, *, release: SkillRelease, zip_bytes: bytes) -> None:
        self._ensure_skills_dir()
        dest = self._skill_dir(release.ref)
        dest.parent.mkdir(parents=True, exist_ok=True)

        tmp_root = self.skills_dir / ".tmp"
        tmp_root.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="skilldock-", dir=tmp_root) as td:
            unpack_root = Path(td) / "unpacked"
            _safe_extract_zip(zip_bytes, unpack_root)

            source_root = unpack_root
            if not (source_root / "SKILL.md").is_file():
                children = [p for p in unpack_root.iterdir()]
                if len(children) == 1 and children[0].is_dir() and (children[0] / "SKILL.md").is_file():
                    source_root = children[0]
                else:
                    raise SkilldockError(
                        f"Archive for {release.ref.key}@{release.version} does not contain SKILL.md at root."
                    )

            backup = dest.with_name(dest.name + ".skilldock-backup")
            had_existing = dest.exists()
            if backup.exists():
                shutil.rmtree(backup, ignore_errors=True)
            if had_existing:
                dest.rename(backup)

            try:
                shutil.move(str(source_root), str(dest))
                self._write_installed_meta(dest, release)
            except Exception:
                if dest.exists():
                    shutil.rmtree(dest, ignore_errors=True)
                if had_existing and backup.exists():
                    backup.rename(dest)
                raise
            finally:
                if backup.exists():
                    shutil.rmtree(backup, ignore_errors=True)

    def _remove_skill(self, ref: SkillRef) -> None:
        skill_dir = self._skill_dir(ref)
        if skill_dir.exists():
            shutil.rmtree(skill_dir, ignore_errors=True)
        ns_dir = skill_dir.parent
        if ns_dir.exists() and ns_dir.is_dir():
            try:
                next(ns_dir.iterdir())
            except StopIteration:
                ns_dir.rmdir()

    def _find_unresolvable_direct_skills(self, direct_requirements: dict[str, str]) -> dict[str, str]:
        failures: dict[str, str] = {}
        for key, requirement in sorted(direct_requirements.items()):
            try:
                resolve_dependency_graph(direct_requirements={key: requirement}, repo=self.repo)
            except SkilldockError as e:
                reason = str(e)
                if not _is_release_unavailable_error(reason):
                    raise
                failures[key] = reason
        return failures

    def _reconcile(self, *, direct_requirements: dict[str, str]) -> ReconcileResult:
        self._ensure_skills_dir()
        current_lock = self._load_lock()
        current_skills = current_lock.get("skills", {})
        if not isinstance(current_skills, dict):
            current_skills = {}

        cleaned_direct: dict[str, str] = {}
        for key, req in direct_requirements.items():
            ref = parse_skill_ref(key)
            cleaned_direct[ref.key] = normalize_requirement(req)

        warnings: list[str] = []
        effective_direct = dict(cleaned_direct)
        while True:
            if not effective_direct:
                resolved = {}
                break
            try:
                resolved, _ = resolve_dependency_graph(direct_requirements=effective_direct, repo=self.repo)
                break
            except SkilldockError as e:
                msg = str(e)
                m = re.search(r"Skill not found or not visible:\s*([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)", msg)
                missing_key = m.group(1) if m else None
                if missing_key is None:
                    m = re.search(
                        r"No release found for\s*([A-Za-z0-9._-]+/[A-Za-z0-9._-]+)\s+that satisfies constraints:",
                        msg,
                    )
                    missing_key = m.group(1) if m else None
                if missing_key and missing_key in effective_direct:
                    warnings.append(f"Skipping missing direct skill: {missing_key}")
                    effective_direct.pop(missing_key, None)
                    continue
                unresolvable = self._find_unresolvable_direct_skills(effective_direct)
                if unresolvable:
                    for key in sorted(unresolvable):
                        warnings.append(f"Skipping unresolved direct skill: {key} ({unresolvable[key]})")
                        effective_direct.pop(key, None)
                    continue
                raise

        installed: list[str] = []
        updated: list[str] = []
        unchanged: list[str] = []
        removed: list[str] = []

        for key in sorted(resolved):
            rel = resolved[key]
            skill_dir = self._skill_dir(rel.ref)
            meta = self._read_installed_meta(skill_dir)
            current_version: str | None = None
            if isinstance(meta, dict) and isinstance(meta.get("version"), str):
                current_version = meta["version"].strip() or None
            if current_version is None:
                lock_item = current_skills.get(key)
                if isinstance(lock_item, dict) and isinstance(lock_item.get("version"), str):
                    current_version = lock_item["version"].strip() or None

            if skill_dir.exists() and current_version and compare_versions(current_version, rel.version) == 0:
                unchanged.append(key)
                continue

            try:
                zip_bytes = self.repo.download_archive(rel)
            except SkilldockError as e:
                missing_release = _parse_missing_download_url_error(str(e))
                if missing_release is None:
                    raise
                missing_key, missing_version = missing_release
                warnings.append(f"Skipping release without download URL: {missing_key}@{missing_version}")
                continue
            existed = skill_dir.exists() or current_version is not None
            self._install_archive(release=rel, zip_bytes=zip_bytes)

            if existed:
                updated.append(key)
            else:
                installed.append(key)

        for key in sorted(current_skills.keys()):
            if key in resolved:
                continue
            ref = parse_skill_ref(key)
            self._remove_skill(ref)
            removed.append(key)

        self._save_manifest(effective_direct)
        self._save_lock(resolved)

        return ReconcileResult(
            installed=tuple(installed),
            updated=tuple(updated),
            removed=tuple(removed),
            unchanged=tuple(unchanged),
            warnings=tuple(warnings),
            manifest_path=self.manifest_path,
            lock_path=self.lock_path,
        )
