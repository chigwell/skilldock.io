import io
import tempfile
import unittest
import zipfile
from pathlib import Path

from skilldock.skill_package import SkillPackageError, package_skill


class TestSkillPackage(unittest.TestCase):
    def test_package_uses_explicit_top_level_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "example_skill"
            root.mkdir(parents=True)
            (root / "SKILL.md").write_text("# Example\n", encoding="utf-8")
            (root / "fetch_example.py").write_text("print('ok')\n", encoding="utf-8")

            pkg = package_skill(root, top_level_dir="my-skill")

            with zipfile.ZipFile(io.BytesIO(pkg.zip_bytes), "r") as zf:
                names = sorted(zf.namelist())

            self.assertEqual(names, ["my-skill/SKILL.md", "my-skill/fetch_example.py"])

    def test_package_defaults_to_source_folder_name(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "example_skill"
            root.mkdir(parents=True)
            (root / "SKILL.md").write_text("# Example\n", encoding="utf-8")

            pkg = package_skill(root)

            with zipfile.ZipFile(io.BytesIO(pkg.zip_bytes), "r") as zf:
                names = zf.namelist()

            self.assertIn("example_skill/SKILL.md", names)

    def test_package_rejects_invalid_top_level_dir(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "example_skill"
            root.mkdir(parents=True)
            (root / "SKILL.md").write_text("# Example\n", encoding="utf-8")

            with self.assertRaises(SkillPackageError):
                package_skill(root, top_level_dir="nested/path")


if __name__ == "__main__":
    unittest.main()
