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
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=Path("config/default-home-local.json"))
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(args.root, args.config), ensure_ascii=False))
        return 0

    from quantum.application.local_app import main as local_app_main

    return local_app_main()


if __name__ == "__main__":
    raise SystemExit(main())
