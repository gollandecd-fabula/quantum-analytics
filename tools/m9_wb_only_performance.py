from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
from typing import Callable, Sequence


TITLE = "M9 WB-Only Performance Regression"
PROBE_MARKETPLACE = "WILDBERRIES"


@dataclass(frozen=True)
class ProbeResult:
    root: str
    iterations: int
    samples_seconds: tuple[float, ...]
    median_seconds: float


@dataclass(frozen=True)
class PerformanceComparison:
    status: str
    baseline: ProbeResult
    candidate: ProbeResult
    max_ratio: float
    absolute_slack_seconds: float
    allowed_seconds: float
    observed_ratio: float


def _probe_once(root: Path, iterations: int) -> float:
    code = """
import json
from pathlib import Path
import sys
import time

root = Path(sys.argv[1]).resolve()
iterations = int(sys.argv[2])
sys.path.insert(0, str(root / "src"))
from quantum.adapters import build_default_marketplace_registry, normalize_marketplace_id

registry = build_default_marketplace_registry()
if "WILDBERRIES" not in registry.registered_marketplaces():
    raise RuntimeError("WILDBERRIES_DEFAULT_ADAPTER_REQUIRED")
values = ("wb", "Wildberries", "future-market", "WILDBERRIES")
started = time.perf_counter()
for index in range(iterations):
    normalize_marketplace_id(values[index % len(values)])
    registry.resolve("WILDBERRIES")
elapsed = time.perf_counter() - started
print(json.dumps({"elapsed_seconds": elapsed}, sort_keys=True))
"""
    completed = subprocess.run(
        [sys.executable, "-c", code, str(root), str(iterations)],
        cwd=root,
        check=False,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"WB-only performance probe failed for {root}: "
            f"{completed.stderr.strip() or completed.stdout.strip()}"
        )
    payload = json.loads(completed.stdout)
    return float(payload["elapsed_seconds"])


def run_probe(
    root: Path,
    *,
    iterations: int = 50_000,
    repeats: int = 5,
    probe_once: Callable[[Path, int], float] = _probe_once,
) -> ProbeResult:
    samples = tuple(probe_once(root.resolve(), iterations) for _ in range(repeats))
    return ProbeResult(
        root=str(root.resolve()),
        iterations=iterations,
        samples_seconds=samples,
        median_seconds=float(statistics.median(samples)),
    )


def compare_performance(
    baseline_root: Path,
    candidate_root: Path,
    *,
    iterations: int = 50_000,
    repeats: int = 5,
    max_ratio: float = 1.75,
    absolute_slack_seconds: float = 0.25,
    probe_once: Callable[[Path, int], float] = _probe_once,
) -> PerformanceComparison:
    baseline = run_probe(
        baseline_root,
        iterations=iterations,
        repeats=repeats,
        probe_once=probe_once,
    )
    candidate = run_probe(
        candidate_root,
        iterations=iterations,
        repeats=repeats,
        probe_once=probe_once,
    )
    allowed = max(
        baseline.median_seconds * max_ratio,
        baseline.median_seconds + absolute_slack_seconds,
    )
    ratio = (
        candidate.median_seconds / baseline.median_seconds
        if baseline.median_seconds > 0
        else float("inf")
    )
    return PerformanceComparison(
        status="PASS" if candidate.median_seconds <= allowed else "FAIL",
        baseline=baseline,
        candidate=candidate,
        max_ratio=max_ratio,
        absolute_slack_seconds=absolute_slack_seconds,
        allowed_seconds=allowed,
        observed_ratio=ratio,
    )


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    encoded = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(encoded)
        temporary = Path(handle.name)
    temporary.replace(path)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=TITLE)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--iterations", type=int, default=50_000)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--max-ratio", type=float, default=1.75)
    parser.add_argument("--absolute-slack-seconds", type=float, default=0.25)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    comparison = compare_performance(
        args.baseline,
        args.candidate,
        iterations=args.iterations,
        repeats=args.repeats,
        max_ratio=args.max_ratio,
        absolute_slack_seconds=args.absolute_slack_seconds,
    )
    payload = {
        "milestone": "M9",
        "title": TITLE,
        "status": comparison.status,
        "probe_marketplace": PROBE_MARKETPLACE,
        "release_scope": "WB_ONLY",
        "baseline": asdict(comparison.baseline),
        "candidate": asdict(comparison.candidate),
        "max_ratio": comparison.max_ratio,
        "absolute_slack_seconds": comparison.absolute_slack_seconds,
        "allowed_seconds": comparison.allowed_seconds,
        "observed_ratio": comparison.observed_ratio,
        "marketplace_write_enabled": False,
        "release_authorized": False,
    }
    _atomic_json(args.output, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0 if comparison.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
