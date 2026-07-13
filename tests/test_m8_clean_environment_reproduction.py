from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools import m8_clean_environment_reproduction as m8


class M8CleanEnvironmentTests(unittest.TestCase):
    def test_path_boundary_is_component_safe(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "sandbox"
            root.mkdir()
            self.assertTrue(m8.path_is_within(root / "home", root))
            self.assertFalse(m8.path_is_within(root.parent / "sandbox-escape", root))

    def test_repository_residue_is_fail_closed_and_git_is_ignored(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / ".git" / "objects").mkdir(parents=True)
            (root / ".git" / "objects" / "ignored.pyc").write_bytes(b"ignored")
            (root / "src").mkdir()
            (root / "src" / "module.py").write_text("VALUE = 1\n", encoding="utf-8")
            self.assertEqual(m8.collect_repo_residue(root), [])
            (root / "src" / "__pycache__").mkdir()
            (root / "src" / "__pycache__" / "module.pyc").write_bytes(b"cache")
            self.assertEqual(
                m8.collect_repo_residue(root), ["src/__pycache__/" ]
            )

    def test_environment_rejects_external_cache_and_profile_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "checkout"
            sandbox = Path(temporary) / "sandbox"
            (root / "src").mkdir(parents=True)
            sandbox.mkdir()
            environment = {
                "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUTF8": "1",
                "PYTHONPATH": str(root / "src"),
                "HOME": str(sandbox / "home"),
                "TMPDIR": str(sandbox / "tmp"),
                "XDG_CACHE_HOME": str(sandbox / "cache"),
                "PIP_CACHE_DIR": str(Path(temporary) / "external-cache"),
            }
            with mock.patch.object(m8.site, "ENABLE_USER_SITE", False):
                findings = m8.environment_findings(
                    root=root,
                    sandbox=sandbox,
                    platform_label="linux",
                    environment=environment,
                )
            self.assertEqual(
                findings,
                [
                    "ENV_PATH_OUTSIDE_SANDBOX:PIP_CACHE_DIR="
                    + str((Path(temporary) / "external-cache").resolve())
                ],
            )

    def test_report_preserves_release_and_marketplace_blocks(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "checkout"
            sandbox = Path(temporary) / "sandbox"
            (root / "src").mkdir(parents=True)
            for name in ("home", "tmp", "cache", "pip-cache"):
                (sandbox / name).mkdir(parents=True)
            environment = {
                "PYTHONNOUSERSITE": "1",
                "PYTHONDONTWRITEBYTECODE": "1",
                "PYTHONUTF8": "1",
                "PYTHONPATH": str(root / "src"),
                "HOME": str(sandbox / "home"),
                "TMPDIR": str(sandbox / "tmp"),
                "XDG_CACHE_HOME": str(sandbox / "cache"),
                "PIP_CACHE_DIR": str(sandbox / "pip-cache"),
            }
            with (
                mock.patch.object(m8.site, "ENABLE_USER_SITE", False),
                mock.patch.object(
                    m8,
                    "git_output",
                    side_effect=["a" * 40, ""],
                ),
            ):
                report = m8.build_report(
                    root=root,
                    sandbox=sandbox,
                    expected_sha="a" * 40,
                    platform_label="linux",
                    environment=environment,
                )
            self.assertEqual(report["status"], "PASS")
            self.assertEqual(report["release_state"], "RELEASE_BLOCKED")
            self.assertFalse(report["marketplace_write_enabled"])
            self.assertFalse(report["merge_to_main_authorized"])
            self.assertFalse(report["production_release_authorized"])


if __name__ == "__main__":
    unittest.main()
