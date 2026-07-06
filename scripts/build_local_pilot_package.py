from __future__ import annotations

import hashlib
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIST = ROOT / "dist"
PACKAGE = DIST / "quantum-local-pilot-one-click.zip"


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def selected(path: Path) -> bool:
    rel = path.relative_to(ROOT).as_posix()
    if not path.is_file():
        return False
    if "/.git/" in rel or "/__pycache__/" in rel or rel.startswith("dist/"):
        return False
    return rel == "pyproject.toml" or rel == "README.md" or rel.startswith("src/") or rel.startswith("scripts/") or rel.startswith("docs/")


def build_package() -> dict[str, object]:
    DIST.mkdir(exist_ok=True)
    entries = []
    with zipfile.ZipFile(PACKAGE, "w", zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            if not selected(path):
                continue
            rel = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            archive.writestr(rel, data)
            entries.append({"path": rel, "sha256": digest(data), "size_bytes": len(data)})
        archive.writestr(
            "PACKAGE_MANIFEST.json",
            json.dumps({"marketplace_write_enabled": False, "entries": entries}, indent=2, sort_keys=True),
        )
    data = PACKAGE.read_bytes()
    summary = {"package": str(PACKAGE), "sha256": digest(data), "size_bytes": len(data), "entry_count": len(entries)}
    (DIST / "quantum-local-pilot-one-click.summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary


def main() -> None:
    print(json.dumps(build_package(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
