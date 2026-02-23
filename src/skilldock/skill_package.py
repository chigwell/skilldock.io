from __future__ import annotations

import hashlib
import io
import os
import zipfile
from dataclasses import dataclass
from pathlib import Path


DEFAULT_MAX_UPLOAD_BYTES = 10 * 1024 * 1024  # 10 MiB (matches current backend MAX_UPLOAD_BYTES)

# Directory/file names to skip anywhere in the tree.
DEFAULT_EXCLUDE_NAMES = {
    ".git",
    ".hg",
    ".svn",
    ".DS_Store",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".venv",
    "venv",
    "node_modules",
    "dist",
    "build",
    ".idea",
    ".vscode",
}


@dataclass(frozen=True)
class SkillPackage:
    root: Path
    zip_bytes: bytes
    sha256: str
    size_bytes: int
    file_count: int
    warnings: list[str]


class SkillPackageError(RuntimeError):
    pass


def _should_exclude(path: Path, root: Path) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        return True

    parts = rel.parts
    if any(p in DEFAULT_EXCLUDE_NAMES for p in parts):
        return True
    return False


def package_skill(
    root: Path,
    *,
    top_level_dir: str | None = None,
    max_upload_bytes: int = DEFAULT_MAX_UPLOAD_BYTES,
) -> SkillPackage:
    root = root.expanduser().resolve()
    if not root.exists():
        raise SkillPackageError(f"Path does not exist: {root}")
    if not root.is_dir():
        raise SkillPackageError(f"Not a directory: {root}")

    skill_md = root / "SKILL.md"
    if not skill_md.exists():
        raise SkillPackageError(f"Missing required file: {skill_md}")
    if not skill_md.is_file():
        raise SkillPackageError(f"SKILL.md is not a file: {skill_md}")

    files: list[Path] = []
    for p in root.rglob("*"):
        if _should_exclude(p, root):
            continue
        if p.is_symlink():
            # Avoid surprising content and portability issues.
            continue
        if p.is_file():
            files.append(p)

    files.sort(key=lambda p: str(p.relative_to(root)).lower())

    archive_root = (top_level_dir if top_level_dir is not None else root.name).strip()
    if not archive_root:
        raise SkillPackageError("Top-level archive folder name must not be empty.")
    if archive_root in {".", ".."} or "/" in archive_root or "\\" in archive_root:
        raise SkillPackageError(
            "Top-level archive folder name must be a single folder name (no path separators)."
        )

    buf = io.BytesIO()
    file_count = 0
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for p in files:
            rel = p.relative_to(root)
            arcname = f"{archive_root}/{str(rel).replace(os.sep, '/')}"
            zf.write(p, arcname=arcname)
            file_count += 1

    zip_bytes = buf.getvalue()
    size_bytes = len(zip_bytes)
    sha256 = hashlib.sha256(zip_bytes).hexdigest()

    warnings: list[str] = []
    if size_bytes > max_upload_bytes:
        warnings.append(f"Packaged zip is {size_bytes} bytes which exceeds max_upload_bytes={max_upload_bytes}.")

    return SkillPackage(
        root=root,
        zip_bytes=zip_bytes,
        sha256=sha256,
        size_bytes=size_bytes,
        file_count=file_count,
        warnings=warnings,
    )
