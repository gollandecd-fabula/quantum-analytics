from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import traceback
from typing import Any, Mapping

from .any_file_gateway import AnyFileError, atomic_json, intake_file


def _mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise AnyFileError("ANY_FILE_CONFIG_INVALID")
    return value


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the HOME_LOCAL universal safe-file intake gateway"
    )
    parser.add_argument("--file", required=True, type=Path)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--storage-root", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--home-local", action="store_true")
    parser.add_argument("--authority-attested", action="store_true")
    parser.add_argument("--schema-reviewed", action="store_true")
    parser.add_argument("--expected-file-sha256")
    parser.add_argument("--debug-errors", action="store_true")
    return parser


def main() -> int:
    args = _parser().parse_args()
    try:
        if not args.home_local:
            raise AnyFileError("ANY_FILE_HOME_LOCAL_REQUIRED")
        config = _mapping(
            json.loads(args.config.read_text(encoding="utf-8-sig"))
        )
        report = intake_file(
            file_path=args.file,
            config=config,
            storage_root=args.storage_root,
            authority_attested=args.authority_attested,
            schema_reviewed=args.schema_reviewed,
            expected_file_sha256=args.expected_file_sha256,
        )
        atomic_json(args.output, report)
        print(
            json.dumps(
                {
                    "status": report["status"],
                    "output": str(args.output),
                    "detected_format": report["detected_format"],
                },
                ensure_ascii=False,
            )
        )
        return 0 if report["status"].startswith("ACCEPTED_") else 2
    except Exception as exc:
        payload: dict[str, Any] = {
            "status": "ERROR",
            "code": getattr(exc, "code", "ANY_FILE_UNEXPECTED_ERROR"),
            "detail": type(exc).__name__,
        }
        if args.debug_errors:
            payload["message"] = str(exc)
            payload["traceback"] = traceback.format_exc()
        print(json.dumps(payload, ensure_ascii=False), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
