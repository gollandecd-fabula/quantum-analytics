from __future__ import annotations

import argparse
import json
from pathlib import Path


def self_test(root: Path, config: Path) -> dict[str, object]:
    checks: dict[str, bool] = {}
    diagnostics: dict[str, object] = {}
    try:
        import tkinter

        version = str(tkinter.TkVersion)
        checks["tkinter_available"] = True
    except ImportError as exc:
        version = None
        checks["tkinter_available"] = False
        diagnostics["tkinter_error"] = type(exc).__name__
    try:
        from quantum.application.local_runtime import (
            self_test as finance_center_self_test,
        )

        finance_center = finance_center_self_test(root, config)
    except Exception as exc:  # pragma: no cover - defensive boundary
        finance_center = {
            "status": "FINANCE_CENTER_SELF_TEST_FAILED",
            "detail": type(exc).__name__,
        }
    finance_status = (
        finance_center.get("status")
        if isinstance(finance_center, dict)
        else None
    )
    checks["finance_center"] = (
        finance_status == "FINANCE_CENTER_SELF_TEST_PASS"
    )
    try:
        from quantum.application.shortcut_repair import (
            repair_legacy_shortcuts,
        )

        checks["shortcut_repair_available"] = callable(
            repair_legacy_shortcuts
        )
    except Exception as exc:
        checks["shortcut_repair_available"] = False
        diagnostics["shortcut_repair_error"] = type(exc).__name__
    checks["root_exists"] = root.resolve().is_dir()
    checks["config_exists"] = config.resolve().is_file()
    checks["marketplace_writes_disabled"] = True
    passed = all(checks.values())
    configuration_required = (
        finance_status == "FINANCE_CENTER_SELF_TEST_CONFIGURATION_REQUIRED"
        and all(
            value is True
            for name, value in checks.items()
            if name != "finance_center"
        )
    )
    status = (
        "DESKTOP_CENTER_SELF_TEST_PASS"
        if passed
        else (
            "DESKTOP_CENTER_SELF_TEST_CONFIGURATION_REQUIRED"
            if configuration_required
            else "DESKTOP_CENTER_SELF_TEST_FAILED"
        )
    )
    return {
        "status": status,
        "checks": checks,
        "diagnostics": diagnostics,
        "tkinter_version": version,
        "finance_center": finance_center,
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
        result = self_test(args.root, args.config)
        print(json.dumps(result, ensure_ascii=False))
        if result["status"] == "DESKTOP_CENTER_SELF_TEST_PASS":
            return 0
        if result["status"] == "DESKTOP_CENTER_SELF_TEST_CONFIGURATION_REQUIRED":
            return 4
        return 2

    from quantum.application.shortcut_repair import repair_legacy_shortcuts
    from quantum.application.local_runtime import main as finance_center_main

    repair_legacy_shortcuts(args.root)
    return finance_center_main(root=args.root, config=args.config)


if __name__ == "__main__":
    raise SystemExit(main())
