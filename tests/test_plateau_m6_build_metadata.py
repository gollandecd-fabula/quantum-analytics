from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from zipfile import ZipFile


ROOT = Path(__file__).resolve().parents[1]


class PlateauM6BuildMetadataTests(unittest.TestCase):
    def test_metadata_describes_actual_desktop_runtime(self) -> None:
        config = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
        self.assertEqual(
            "setuptools.build_meta",
            config["build-system"]["build-backend"],
        )
        self.assertEqual(
            ["setuptools==80.9.0"],
            config["build-system"]["requires"],
        )
        project = config["project"]
        self.assertNotEqual("0.0.1", project["version"])
        self.assertIn("desktop", project["description"].casefold())
        scripts = project["scripts"]
        self.assertEqual(
            "quantum.application.desktop_center:main",
            scripts["quantum-desktop"],
        )
        self.assertNotIn("quantum-api", scripts)
        self.assertNotIn("quantum-worker", scripts)
        self.assertFalse(config["tool"]["quantum"]["marketplace_write_enabled"])

    def test_standard_backend_builds_installable_desktop_wheel(self) -> None:
        generated = (
            ROOT / "build",
            ROOT / "src" / "quantum_analytics.egg-info",
        )
        try:
            with tempfile.TemporaryDirectory() as directory:
                environment = os.environ.copy()
                environment.update(
                    {
                        "PIP_DISABLE_PIP_VERSION_CHECK": "1",
                        "PIP_NO_INPUT": "1",
                    }
                )
                completed = subprocess.run(
                    [
                        sys.executable,
                        "-m",
                        "pip",
                        "wheel",
                        "--no-deps",
                        "--no-cache-dir",
                        "--wheel-dir",
                        directory,
                        str(ROOT),
                    ],
                    cwd=ROOT,
                    env=environment,
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertEqual(
                    0,
                    completed.returncode,
                    completed.stdout + "\n" + completed.stderr,
                )
                wheels = tuple(Path(directory).glob("quantum_analytics-*.whl"))
                self.assertEqual(1, len(wheels), completed.stdout)
                with ZipFile(wheels[0]) as archive:
                    names = set(archive.namelist())
                    entry_name = next(
                        name
                        for name in names
                        if name.endswith(".dist-info/entry_points.txt")
                    )
                    metadata_name = next(
                        name
                        for name in names
                        if name.endswith(".dist-info/METADATA")
                    )
                    entries = archive.read(entry_name).decode("utf-8")
                    metadata = archive.read(metadata_name).decode("utf-8")
                self.assertIn(
                    "quantum/application/desktop_center.py",
                    names,
                )
                self.assertIn("quantum-desktop", entries)
                self.assertNotIn("quantum-api", entries)
                self.assertNotIn("quantum-worker", entries)
                self.assertIn("Version: 0.9.0rc1", metadata)
        finally:
            for path in generated:
                if path.exists():
                    shutil.rmtree(path)

    def test_primary_docs_do_not_describe_obsolete_cloud_product(self) -> None:
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        state = (ROOT / "docs/governance/CURRENT_STATE.md").read_text(
            encoding="utf-8"
        )
        for obsolete in (
            "Hard pilot target: `2026-07-08`",
            "Railway",
            "Vercel",
            "Cloudflare",
            "Modular monolith with two runtime entry points",
            "r3-real-commercial-data-pilot-v1",
        ):
            self.assertNotIn(obsolete, readme + state)
        self.assertIn("RELEASE_BLOCKED", readme)
        self.assertIn("PLATEAU_RED_TEAM_IN_PROGRESS", state)


if __name__ == "__main__":
    unittest.main()
