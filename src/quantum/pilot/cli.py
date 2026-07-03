from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from ._errors import KNOWN_PILOT_ERRORS, error_code
from .purge import purge_workspace
from .runner import run_manifest
from .validation import validate_manifest


def _emit(value: Any, *, stream) -> None:
    print(
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ),
        file=stream,
    )


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Quantum local pilot runner")
    subcommands = parser.add_subparsers(dest="command", required=True)

    validate = subcommands.add_parser("validate")
    validate.add_argument("manifest", type=Path)

    run = subcommands.add_parser("run")
    run.add_argument("manifest", type=Path)
    run.add_argument("--workspace", type=Path, required=True)

    purge = subcommands.add_parser("purge")
    purge.add_argument("--workspace", type=Path, required=True)
    purge.add_argument("--tenant-id", required=True)
    purge.add_argument("--run-id", required=True)
    purge.add_argument("--purged-at", required=True)
    return parser


def main() -> None:
    args = _parser().parse_args()
    try:
        if args.command == "validate":
            result = validate_manifest(args.manifest)
        elif args.command == "run":
            result = run_manifest(args.manifest, workspace_base=args.workspace)
        else:
            result = purge_workspace(
                workspace_base=args.workspace,
                tenant_id=args.tenant_id,
                run_id=args.run_id,
                purged_at=args.purged_at,
            )
        _emit(result, stream=sys.stdout)
    except KNOWN_PILOT_ERRORS as exc:
        _emit(
            {
                "schema_version": "quantum-local-pilot-error-v1",
                "status": "BLOCKED",
                "error_code": error_code(exc),
                "release_state": "RELEASE_BLOCKED",
            },
            stream=sys.stderr,
        )
        raise SystemExit(2) from None
    except Exception:
        _emit(
            {
                "schema_version": "quantum-local-pilot-error-v1",
                "status": "BLOCKED",
                "error_code": "PILOT_INTERNAL_ERROR",
                "release_state": "RELEASE_BLOCKED",
            },
            stream=sys.stderr,
        )
        raise SystemExit(3) from None


if __name__ == "__main__":
    main()
