from __future__ import annotations

import compileall
import os
import subprocess
import sys
from pathlib import Path


FORBIDDEN_SOURCE_MARKERS = (
    "ghp_",
    "github_pat_",
    "BEGIN PRIVATE KEY",
    "marketplace_write_enabled = true",
)


def project_root() -> Path:
    return Path(__file__).resolve().parents[3]


def scan_forbidden_markers(root: Path) -> None:
    violations: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        if any(part in {".git", "__pycache__"} for part in path.parts):
            continue
        if path.suffix.lower() not in {".py", ".md", ".toml", ".sql", ".json", ".yaml", ".yml"}:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for marker in FORBIDDEN_SOURCE_MARKERS:
            if marker in text and path.name != "ci.py":
                violations.append(f"{path.relative_to(root)}: {marker}")
    if violations:
        raise RuntimeError("Forbidden source markers:\n" + "\n".join(violations))


def main() -> None:
    root = project_root()
    src = root / "src"

    if not compileall.compile_dir(src, quiet=1):
        raise SystemExit("compileall failed")

    scan_forbidden_markers(root)

    excluded = {
        "test_a0_manifest_diagnostic.py",
        "test_b1a_artifact_manifest.py",
    }
    modules = [
        f"tests.{path.stem}"
        for path in sorted((root / "tests").glob("test_*.py"))
        if path.name not in excluded
    ]
    env = dict(os.environ)
    env["PYTHONPATH"] = str(src)
    result = subprocess.run(
        [sys.executable, "-m", "unittest", "-v", *modules],
        cwd=root,
        env=env,
        check=False,
        text=True,
    )
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()
