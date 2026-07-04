from __future__ import annotations

import base64
import gzip
import hashlib
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
STAGE = ROOT / '.redteam_patch'
WORKFLOW = '.github/workflows/apply-redteam-patch.yml'
ALLOWED_STAGING_PREFIX = '.redteam_patch/'


def git(*args: str) -> str:
    return subprocess.check_output(['git', *args], cwd=ROOT, text=True).strip()


def fail(message: str) -> None:
    raise SystemExit(message)


def safe_path(raw: str) -> Path:
    if not isinstance(raw, str) or not raw or '\\' in raw:
        fail(f'unsafe patch path: {raw!r}')
    candidate = Path(raw)
    if candidate.is_absolute() or any(part in {'', '.', '..'} for part in candidate.parts):
        fail(f'unsafe patch path: {raw!r}')
    resolved = (ROOT / candidate).resolve()
    if not resolved.is_relative_to(ROOT.resolve()):
        fail(f'patch path escaped repository: {raw!r}')
    return resolved


parts = sorted(STAGE.glob('part*.txt'))
if not parts:
    fail('patch parts are missing')
encoded = ''.join(path.read_text(encoding='ascii').strip() for path in parts)
try:
    raw = gzip.decompress(base64.b64decode(encoded, validate=True))
    payload = json.loads(raw.decode('utf-8'))
except Exception as exc:
    fail(f'patch bundle decode failed: {type(exc).__name__}')
if payload.get('format') != 'quantum-redteam-patch-v1':
    fail('unexpected patch bundle format')
ancestor = payload.get('required_ancestor')
if not isinstance(ancestor, str) or len(ancestor) != 40:
    fail('required ancestor is invalid')
subprocess.run(['git', 'merge-base', '--is-ancestor', ancestor, 'HEAD'], cwd=ROOT, check=True)
changed = git('diff', '--name-only', f'{ancestor}..HEAD').splitlines()
for path in changed:
    if path == WORKFLOW or path.startswith(ALLOWED_STAGING_PREFIX):
        continue
    fail(f'unexpected staging change since required ancestor: {path}')
files = payload.get('files')
if not isinstance(files, dict) or not files:
    fail('patch file map is invalid')
for rel, meta in files.items():
    target = safe_path(rel)
    if not isinstance(meta, dict):
        fail(f'invalid metadata for {rel}')
    try:
        data = base64.b64decode(meta['content_b64'], validate=True)
    except Exception as exc:
        fail(f'invalid content for {rel}: {type(exc).__name__}')
    digest = hashlib.sha256(data).hexdigest()
    if digest != meta.get('sha256') or len(data) != meta.get('size'):
        fail(f'patch integrity mismatch: {rel}')
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name + '.redteam.tmp')
    temporary.write_bytes(data)
    temporary.replace(target)
for rel, meta in files.items():
    target = safe_path(rel)
    data = target.read_bytes()
    if hashlib.sha256(data).hexdigest() != meta['sha256'] or len(data) != meta['size']:
        fail(f'post-write verification failed: {rel}')
print(json.dumps({'status': 'PATCH_APPLIED', 'files': len(files)}, sort_keys=True))
