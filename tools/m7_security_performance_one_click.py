from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import statistics
import subprocess
import sys
import tempfile
from typing import Callable, Sequence

MILESTONE = "M7"
TITLE = "Security, Performance and One-Click"
AUDIT_VERSION = 1
DEFAULT_BASELINE_SHA = "0972d02312bdee3aae3583dc6d9caf369622a57d"


@dataclass(frozen=True)
class Finding:
    finding_id: str
    severity: str
    gate: str
    message: str
    path: str | None = None


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


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _finding(
    finding_id: str,
    severity: str,
    gate: str,
    message: str,
    path: Path | None = None,
) -> Finding:
    return Finding(
        finding_id=finding_id,
        severity=severity,
        gate=gate,
        message=message,
        path=None if path is None else path.as_posix(),
    )


def audit_security(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    pyproject = root / "pyproject.toml"
    one_click = root / "scripts/windows/one_click_home_local.ps1"
    importer = root / "scripts/windows/import_source.ps1"
    installer = root / "scripts/windows/install_home_local.ps1"
    builder = root / "scripts/windows/build_local_production.ps1"

    required_files = (pyproject, one_click, importer, installer, builder)
    for path in required_files:
        if not path.is_file():
            findings.append(
                _finding(
                    "M7-S001",
                    "P1",
                    "SECURITY",
                    "Required one-click security surface is missing.",
                    path,
                )
            )
    if findings:
        return findings

    pyproject_text = _read(pyproject)
    if "marketplace_write_enabled = false" not in pyproject_text:
        findings.append(
            _finding(
                "M7-S002",
                "P0",
                "SECURITY",
                "Repository policy no longer proves that marketplace writes are disabled.",
                pyproject,
            )
        )

    one_click_text = _read(one_click)
    importer_text = _read(importer)
    installer_text = _read(installer)
    builder_text = _read(builder)

    forbidden_launcher_defaults = (
        "SkipDefenderScan = $true",
        "AuthorityAttested = $true",
        "SchemaReviewed = $true",
    )
    for token in forbidden_launcher_defaults:
        if token in one_click_text or token in importer_text:
            findings.append(
                _finding(
                    "M7-S003",
                    "P0",
                    "SECURITY",
                    f"Launcher contains a forbidden implicit authorization default: {token}",
                    one_click if token in one_click_text else importer,
                )
            )

    required_security_tokens = {
        one_click: (
            "Assert-LocalPathSafety -Path $PackageRoot",
            "Assert-LocalPathSafety -Path $TargetRoot",
            "-not $AuthorityAttested -or -not $SchemaReviewed",
            "launchers never attest on your behalf",
            "Test-PathWithin -Child $directory -Parent $Root",
        ),
        importer: (
            "Microsoft Defender scan failed or reported a threat.",
            "Non-interactive mode requires explicit $Expected attestation switch.",
            "ExpectedFileSha256",
            "PreScannedEvidenceSha256",
        ),
        installer: (
            'release_state -ne "RELEASE_BLOCKED"',
            "marketplace_write_enabled -ne $false",
            "Assert-PackageManifest -Root $SourceRoot",
            "Manifest hash mismatch",
        ),
        builder: (
            'release_state = "RELEASE_BLOCKED"',
            "marketplace_write_enabled = $false",
        ),
    }
    for path, tokens in required_security_tokens.items():
        text = _read(path)
        for token in tokens:
            if token not in text:
                findings.append(
                    _finding(
                        "M7-S004",
                        "P1",
                        "SECURITY",
                        f"Required fail-closed control is missing: {token}",
                        path,
                    )
                )

    source_root = root / "src/quantum"
    if not source_root.is_dir():
        findings.append(
            _finding(
                "M7-S005",
                "P1",
                "SECURITY",
                "Quantum runtime source directory is missing.",
                source_root,
            )
        )
        return findings

    write_enabled_pattern = re.compile(
        r"marketplace_write_enabled\s*[:=]\s*(?:True|true|\$true)",
        re.IGNORECASE,
    )
    shell_true_pattern = re.compile(r"\bshell\s*=\s*True\b")
    network_write_patterns = (
        "requests.post(",
        "requests.put(",
        "requests.patch(",
        "httpx.post(",
        "httpx.put(",
        "urllib.request.urlopen(",
    )
    for path in sorted(source_root.rglob("*.py")):
        text = _read(path)
        if write_enabled_pattern.search(text):
            findings.append(
                _finding(
                    "M7-S006",
                    "P0",
                    "SECURITY",
                    "Runtime source contains a write-enabled marketplace value.",
                    path,
                )
            )
        if shell_true_pattern.search(text):
            findings.append(
                _finding(
                    "M7-S007",
                    "P1",
                    "SECURITY",
                    "Runtime source enables shell=True.",
                    path,
                )
            )
        for token in network_write_patterns:
            if token in text:
                findings.append(
                    _finding(
                        "M7-S008",
                        "P1",
                        "SECURITY",
                        f"Runtime source contains an unapproved network-write primitive: {token}",
                        path,
                    )
                )

    return findings


def audit_one_click(root: Path) -> list[Finding]:
    findings: list[Finding] = []
    one_click = root / "scripts/windows/one_click_home_local.ps1"
    installer = root / "scripts/windows/install_home_local.ps1"
    if not one_click.is_file() or not installer.is_file():
        return [
            _finding(
                "M7-O001",
                "P1",
                "ONE_CLICK",
                "One-click launcher or installer is missing.",
                one_click if not one_click.is_file() else installer,
            )
        ]

    one_click_text = _read(one_click)
    installer_text = _read(installer)
    ordered_tokens = (
        "& $installer -SourceRoot $PackageRoot -TargetRoot $TargetRoot",
        "$Config = Invoke-ConfigurationWizard",
        "& $importer @importArguments",
    )
    positions: list[int] = []
    for token in ordered_tokens:
        position = one_click_text.find(token)
        if position < 0:
            findings.append(
                _finding(
                    "M7-O002",
                    "P1",
                    "ONE_CLICK",
                    f"One-click sequence token is missing: {token}",
                    one_click,
                )
            )
        positions.append(position)
    if all(position >= 0 for position in positions) and positions != sorted(positions):
        findings.append(
            _finding(
                "M7-O003",
                "P1",
                "ONE_CLICK",
                "One-click install/configure/import sequence is not deterministic.",
                one_click,
            )
        )

    user_error_tokens = (
        "Python 3.12 or newer was not found.",
        "File is required in non-interactive mode.",
        "The supplied configuration is not ready:",
        "Quantum did not create the expected pilot result:",
        "Source selection cancelled.",
    )
    combined = one_click_text + "\n" + _read(root / "scripts/windows/import_source.ps1")
    for token in user_error_tokens:
        if token not in combined:
            findings.append(
                _finding(
                    "M7-O004",
                    "P1",
                    "ONE_CLICK",
                    f"Actionable user-facing error contract is missing: {token}",
                    one_click,
                )
            )

    installer_checks = (
        'set "quantum_exit=%errorlevel%"',
        'exit /b %quantum_exit%',
        "Existing config, data and output directories were preserved.",
        "$packageManifest = Assert-PackageManifest -Root $SourceRoot",
        "New-Item -ItemType Directory -Path $TargetRoot",
    )
    for token in installer_checks:
        if token not in installer_text:
            findings.append(
                _finding(
                    "M7-O005",
                    "P1",
                    "ONE_CLICK",
                    f"Installer reproducibility contract is missing: {token}",
                    installer,
                )
            )
    manifest_position = installer_text.find(
        "$packageManifest = Assert-PackageManifest -Root $SourceRoot"
    )
    mutation_position = installer_text.find("New-Item -ItemType Directory -Path $TargetRoot")
    if (
        manifest_position >= 0
        and mutation_position >= 0
        and manifest_position >= mutation_position
    ):
        findings.append(
            _finding(
                "M7-O006",
                "P1",
                "ONE_CLICK",
                "Package verification occurs after target mutation.",
                installer,
            )
        )

    return findings


def audit_repository(root: Path) -> dict[str, object]:
    root = root.resolve()
    findings = [*audit_security(root), *audit_one_click(root)]
    blocking = [finding for finding in findings if finding.severity in {"P0", "P1"}]
    return {
        "audit_version": AUDIT_VERSION,
        "milestone": MILESTONE,
        "title": TITLE,
        "root": str(root),
        "status": "PASS" if not blocking else "FAIL",
        "blocking_findings": [asdict(finding) for finding in blocking],
        "all_findings": [asdict(finding) for finding in findings],
        "security_p0_p1_open": len(blocking),
        "marketplace_write_enabled": False,
        "release_authorized": False,
    }


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
values = ("wb", "Wildberries", "ozon", "future-market")
started = time.perf_counter()
for index in range(iterations):
    normalize_marketplace_id(values[index % len(values)])
    registry.resolve("WILDBERRIES" if index % 2 == 0 else "OZON")
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
            f"Performance probe failed for {root}: "
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
    status = "PASS" if candidate.median_seconds <= allowed else "FAIL"
    return PerformanceComparison(
        status=status,
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


def _performance_payload(comparison: PerformanceComparison) -> dict[str, object]:
    return {
        "milestone": MILESTONE,
        "title": TITLE,
        "status": comparison.status,
        "baseline": asdict(comparison.baseline),
        "candidate": asdict(comparison.candidate),
        "max_ratio": comparison.max_ratio,
        "absolute_slack_seconds": comparison.absolute_slack_seconds,
        "allowed_seconds": comparison.allowed_seconds,
        "observed_ratio": comparison.observed_ratio,
        "marketplace_write_enabled": False,
        "release_authorized": False,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=TITLE)
    subparsers = parser.add_subparsers(dest="command", required=True)

    audit = subparsers.add_parser("audit")
    audit.add_argument("--root", type=Path, required=True)
    audit.add_argument("--output", type=Path, required=True)

    compare = subparsers.add_parser("compare")
    compare.add_argument("--baseline", type=Path, required=True)
    compare.add_argument("--candidate", type=Path, required=True)
    compare.add_argument("--output", type=Path, required=True)
    compare.add_argument("--iterations", type=int, default=50_000)
    compare.add_argument("--repeats", type=int, default=5)
    compare.add_argument("--max-ratio", type=float, default=1.75)
    compare.add_argument("--absolute-slack-seconds", type=float, default=0.25)

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "audit":
        payload = audit_repository(args.root)
        _atomic_json(args.output, payload)
        print(json.dumps(payload, sort_keys=True))
        return 0 if payload["status"] == "PASS" else 1

    comparison = compare_performance(
        args.baseline,
        args.candidate,
        iterations=args.iterations,
        repeats=args.repeats,
        max_ratio=args.max_ratio,
        absolute_slack_seconds=args.absolute_slack_seconds,
    )
    payload = _performance_payload(comparison)
    _atomic_json(args.output, payload)
    print(json.dumps(payload, sort_keys=True))
    return 0 if comparison.status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
