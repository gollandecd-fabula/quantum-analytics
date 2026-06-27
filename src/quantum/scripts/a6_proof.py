from __future__ import annotations

import argparse
import json
import shutil
from dataclasses import asdict
from pathlib import Path

from quantum.ingestion.proof_pipeline import (
    build_metric_evidence,
    import_csv_for_proof,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run Quantum A6 synthetic data proof")
    parser.add_argument("--valid", type=Path, required=True)
    parser.add_argument("--unknown", type=Path, required=True)
    parser.add_argument("--semantic-drift", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    if args.output.exists():
        shutil.rmtree(args.output)
    args.output.mkdir(parents=True)

    common = {
        "raw_storage_root": args.output / "raw",
        "quarantine_root": args.output / "quarantine",
        "ledger_path": args.output / "ledger/events.json",
        "source_records_path": args.output / "ledger/source-records.jsonl",
    }

    first = import_csv_for_proof(source_path=args.valid, **common)
    replay = import_csv_for_proof(source_path=args.valid, **common)
    unknown = import_csv_for_proof(source_path=args.unknown, **common)
    semantic = import_csv_for_proof(source_path=args.semantic_drift, **common)

    metric = build_metric_evidence(
        ledger_path=common["ledger_path"],
        source_file_sha256=first.file_sha256,
        source_records_path=common["source_records_path"],
    )

    summary = {
        "first_import": asdict(first),
        "replay_import": asdict(replay),
        "unknown_schema": asdict(unknown),
        "semantic_drift": asdict(semantic),
        "metric_evidence": metric,
    }

    (args.output / "proof-summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(summary, ensure_ascii=False))


if __name__ == "__main__":
    main()
