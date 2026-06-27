from __future__ import annotations

import argparse
import json
import sys
from typing import Any


def technical_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "component": "quantum-worker",
        "mode": "foundation",
        "marketplace_write_enabled": False,
    }


def run_once() -> dict[str, Any]:
    # No queue or database is configured in Foundation.
    return {
        "status": "idle",
        "processed": 0,
        "reason": "NO_DURABLE_QUEUE_CONFIGURED",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Quantum Worker foundation runtime")
    parser.add_argument("--once", action="store_true", default=True)
    parser.parse_args()
    print(json.dumps({"health": technical_health(), "run": run_once()}))
    sys.exit(0)


if __name__ == "__main__":
    main()
