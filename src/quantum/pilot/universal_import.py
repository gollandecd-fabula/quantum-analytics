from __future__ import annotations

from .universal_gateway import (
    IntakeDecision,
    UNIVERSAL_IMPORT_SCHEMA_VERSION,
    UniversalImportError,
    classify_payload,
    main,
    register_file,
)

__all__ = [
    "IntakeDecision",
    "UNIVERSAL_IMPORT_SCHEMA_VERSION",
    "UniversalImportError",
    "classify_payload",
    "main",
    "register_file",
]


if __name__ == "__main__":
    raise SystemExit(main())
