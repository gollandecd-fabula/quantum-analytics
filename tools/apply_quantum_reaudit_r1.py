from __future__ import annotations

import base64
import hashlib
import io
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile


ROOT = Path(__file__).resolve().parents[1]
PART_GLOB = "reaudit_part_*.txt"
EXPECTED_BASE64_SIZE = 51_260
EXPECTED_BASE64_SHA256 = (
    "9b3f9e73c8a262d249006e639084e7c95481817ca7f1ef77c36df4b1c2e289c5"
)
EXPECTED_TAR_SIZE = 38_443
EXPECTED_TAR_SHA256 = (
    "1047291bd60c09efcff6c9199c9cf42b472c8ea506fd81e9921c7c8bbb2e859c"
)
EXPECTED_FILES = {
    "src/quantum/application/_finance_center_shell.py": (
        10_315,
        "fe26df69b8af67c13830e0e99c603623802e99567fcba64dfdee1247df91b82e",
    ),
    "src/quantum/application/_finance_center_shared.py": (
        4_129,
        "dea39729bcf9ca34b92358d7beb1190221b162903f0857ac771d3c13a8876a3b",
    ),
    "src/quantum/application/_finance_center_pages.py": (
        34_859,
        "5f6b09598416ebe02ab3461514ea4592edba985e6070e32a8a2957883bb88e10",
    ),
    "src/quantum/application/_finance_profile_outputs.py": (
        18_280,
        "79b70c87a9c0b1ac63f3fcbee3f2474522655793f15395a32e71e0cece2bb044",
    ),
    "src/quantum/application/_finance_center_calculation.py": (
        23_726,
        "63c19b52f693d1137caf2cfc0a6cc82a52a9acab7cd82f2d6508d88f0195afd4",
    ),
    "src/quantum/scripts/ci.py": (
        5_392,
        "23f87c7a1abd2ba3d7fa1225e99c3f683ab9510fa8d6c5997b524c05f8ca8a3f",
    ),
    "src/quantum/reporting/runtime.py": (
        28_513,
        "79ba5322f7df3f1508e6230cdc805ff19f27a076b4ba22b7ac04a768dc80908a",
    ),
    "src/quantum/pilot/windows_runner.py": (
        22_172,
        "d7bcaf505e4337679dd4b10ad9fd679afff653c5b7c1435bfcbff73deb223a66",
    ),
    "tests/integration_manifest_support_m8.py": (
        1_090,
        "141157ef6f94a672ae827ab781c6e98784ef8ed58a1990db4d7d2f70bf119d18",
    ),
    "tests/test_quantum_reaudit_plateau_r1.py": (
        10_573,
        "5c92aa1b4a21ae3f5d5e7cc056bcd9533912b32ec6b4570f3f3ce7c2cee6a096",
    ),
    "docs/evidence/ARTIFACT_MANIFEST_OVERLAY_PILOT_INTEGRATION_R91.json": (
        2_243,
        "1d163fe5b154db3fe751797f7d6cd662404d1b5d5bf96dbfbbe9e3d1a2b3b150",
    ),
}
ALLOWED_MEMBERS = frozenset(EXPECTED_FILES)


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def run(*args: str, env: dict[str, str] | None = None) -> None:
    print("+", " ".join(args), flush=True)
    subprocess.run(args, cwd=ROOT, env=env, check=True)


def read_payload() -> bytes:
    parts = sorted((ROOT / "tools").glob(PART_GLOB))
    expected_names = [f"reaudit_part_{number:02d}.txt" for number in range(13)]
    actual_names = [path.name for path in parts]
    if actual_names != expected_names:
        raise RuntimeError(
            f"PAYLOAD_PART_SET_MISMATCH: expected={expected_names!r} actual={actual_names!r}"
        )
    encoded = b"".join(path.read_bytes() for path in parts)
    if len(encoded) != EXPECTED_BASE64_SIZE:
        raise RuntimeError(
            f"PAYLOAD_BASE64_SIZE_MISMATCH:{len(encoded)}:{EXPECTED_BASE64_SIZE}"
        )
    if sha256_bytes(encoded) != EXPECTED_BASE64_SHA256:
        raise RuntimeError("PAYLOAD_BASE64_SHA256_MISMATCH")
    try:
        payload = base64.b64decode(encoded, validate=True)
    except Exception as exc:  # pragma: no cover - fail-closed diagnostic
        raise RuntimeError("PAYLOAD_BASE64_INVALID") from exc
    if len(payload) != EXPECTED_TAR_SIZE:
        raise RuntimeError(
            f"PAYLOAD_TAR_SIZE_MISMATCH:{len(payload)}:{EXPECTED_TAR_SIZE}"
        )
    if sha256_bytes(payload) != EXPECTED_TAR_SHA256:
        raise RuntimeError("PAYLOAD_TAR_SHA256_MISMATCH")
    return payload


def safe_extract(payload: bytes) -> None:
    with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as archive:
        members = archive.getmembers()
        file_names = []
        for member in members:
            pure = PurePosixPath(member.name)
            if (
                pure.is_absolute()
                or ".." in pure.parts
                or member.issym()
                or member.islnk()
                or member.isdev()
            ):
                raise RuntimeError(f"UNSAFE_TAR_MEMBER:{member.name}")
            if member.isfile():
                file_names.append(member.name)
        if set(file_names) != ALLOWED_MEMBERS:
            raise RuntimeError(
                "PAYLOAD_MEMBER_SET_MISMATCH:"
                f"missing={sorted(ALLOWED_MEMBERS - set(file_names))}:"
                f"unexpected={sorted(set(file_names) - ALLOWED_MEMBERS)}"
            )
        archive.extractall(ROOT, filter="data")


def verify_extracted_files() -> None:
    for relative, (expected_size, expected_sha256) in EXPECTED_FILES.items():
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            raise RuntimeError(f"EXTRACTED_FILE_MISSING_OR_UNSAFE:{relative}")
        data = path.read_bytes()
        if len(data) != expected_size:
            raise RuntimeError(
                f"EXTRACTED_FILE_SIZE_MISMATCH:{relative}:{len(data)}:{expected_size}"
            )
        if sha256_bytes(data) != expected_sha256:
            raise RuntimeError(f"EXTRACTED_FILE_SHA256_MISMATCH:{relative}")


def remove_bootstrap_files() -> None:
    for pattern in ("reaudit_part_*.txt", "reaudit_payload_*.txt"):
        for path in (ROOT / "tools").glob(pattern):
            path.unlink()
    (ROOT / ".github/workflows/apply-quantum-reaudit-r1.yml").unlink(
        missing_ok=True
    )
    Path(__file__).unlink(missing_ok=True)


def verify_source() -> None:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(ROOT / "src")
    run("python", "-m", "compileall", "-q", "src", env=env)
    run(
        "python",
        "-m",
        "unittest",
        "tests.test_quantum_reaudit_plateau_r1",
        "-v",
        env=env,
    )
    run("python", "-m", "quantum.scripts.ci", env=env)


def commit_and_push() -> None:
    branch = os.environ.get("GITHUB_HEAD_REF") or os.environ.get("GITHUB_REF_NAME")
    expected_branch = "tmp/quantum-reaudit-r91-stage"
    if branch != expected_branch:
        raise RuntimeError(f"UNEXPECTED_BRANCH:{branch!r}")
    run("git", "config", "user.name", "quantum-reaudit-bot")
    run("git", "config", "user.email", "quantum-reaudit-bot@users.noreply.github.com")
    run("git", "add", "-A")
    status = subprocess.run(
        ("git", "status", "--porcelain"),
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    if not status.strip():
        raise RuntimeError("NO_REAUDIT_CHANGES_TO_COMMIT")
    print(status, flush=True)
    run("git", "commit", "-m", "fix(reaudit): plateau repair cycle R91")
    run("git", "push", "origin", f"HEAD:{expected_branch}")


def main() -> None:
    payload = read_payload()
    safe_extract(payload)
    verify_extracted_files()
    remove_bootstrap_files()
    verify_source()
    commit_and_push()


if __name__ == "__main__":
    main()
