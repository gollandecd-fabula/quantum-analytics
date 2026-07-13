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
    try:
        from quantum.application.local_runtime import self_test as finance_center_self_test
        finance_center = finance_center_self_test(root, config)
    except Exception as exc:  # pragma: no cover - defensive self-test boundary
        finance_center = {
            "status": "FINANCE_CENTER_SELF_TEST_FAILED",
            "detail": type(exc).__name__,
        }
    try:
        from quantum.application.shortcut_repair import repair_legacy_shortcuts
        shortcut_repair_available = callable(repair_legacy_shortcuts)
    except Exception:
        shortcut_repair_available = False
    return {
        "status": "DESKTOP_CENTER_SELF_TEST_PASS",
        "root_exists": root.resolve().is_dir(),
        "config_exists": config.resolve().is_file(),
        "tkinter_available": version is not None,
        "tkinter_version": version,
        "finance_center": finance_center,
        "shortcut_repair_available": shortcut_repair_available,
        "release_scope": "WB_ONLY",
        "marketplace_write_enabled": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Quantum desktop center")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/default-home-local.json"),
    )
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        print(json.dumps(self_test(args.root, args.config), ensure_ascii=False))
        return 0

    from quantum.application.shortcut_repair import repair_legacy_shortcuts
    from quantum.application.local_runtime import main as finance_center_main

    repair_legacy_shortcuts(args.root)
    return finance_center_main(root=args.root, config=args.config)


if __name__ == "__main__":
    raise SystemExit(main())
