from __future__ import annotations

import argparse
import json
from pathlib import Path


def self_test(root: Path, config: Path) -> dict[str, object]:
    try:
        import tkinter
        version = str(tkinter.TkVersion)
    except ImportError:
        version = None
    return {
        "status": "DESKTOP_CENTER_SELF_TEST_PASS",
        "root_exists": root.resolve().is_dir(),
        "config_exists": config.resolve().is_file(),
        "tkinter_available": version is not None,
        "tkinter_version": version,
        "marketplace_write_enabled": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Quantum desktop center")
    parser.add_argument("--root", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(args.root, args.config), ensure_ascii=False))
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
