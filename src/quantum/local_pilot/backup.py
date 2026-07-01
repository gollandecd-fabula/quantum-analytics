from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from datetime import datetime,timezone
from pathlib import Path


class BackupError(ValueError):
    def __init__(self,code:str)->None:
        super().__init__(code);self.code=code


def _hash(path:Path)->tuple[str,int]:
    digest=hashlib.sha256();size=0
    with path.open("rb") as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b""):
            digest.update(chunk);size+=len(chunk)
    return digest.hexdigest(),size


def _files(root:Path):
    for path in sorted(root.rglob("*")):
        if path.is_symlink():raise BackupError("BACKUP_SYMLINK_FORBIDDEN")
        if path.is_file():yield path


def create_backup(data_root:Path,backup_root:Path,*,encrypted_storage_attested:bool)->Path:
    if not encrypted_storage_attested:raise BackupError("ENCRYPTED_STORAGE_ATTESTATION_REQUIRED")
    source=Path(data_root).resolve();destination=Path(backup_root).resolve()
    if not source.is_dir():raise BackupError("BACKUP_SOURCE_MISSING")
    destination.mkdir(parents=True,exist_ok=True,mode=0o700)
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    snapshot=destination/("quantum-local-"+stamp)
    temp=Path(tempfile.mkdtemp(prefix=".quantum-backup-",dir=destination))
    try:
        payload=temp/"payload";payload.mkdir(mode=0o700)
        for name in ("admission.json","raw","results"):
            item=source/name
            if not item.exists():continue
            target=payload/name
            if item.is_dir():shutil.copytree(item,target,symlinks=False)
            elif item.is_file():shutil.copy2(item,target)
            else:raise BackupError("BACKUP_SOURCE_INVALID")
        entries=[]
        for path in _files(payload):
            digest,size=_hash(path);entries.append([path.relative_to(payload).as_posix(),digest,size])
            os.chmod(path,0o600)
        manifest={"schema_version":"quantum-local-backup-v1","created_at":datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00","Z"),"entries":entries}
        (temp/"manifest.json").write_text(json.dumps(manifest,sort_keys=True,separators=(",",":")),encoding="utf-8")
        os.chmod(temp/"manifest.json",0o600)
        os.replace(temp,snapshot);os.chmod(snapshot,0o700)
        return snapshot
    except Exception:
        shutil.rmtree(temp,ignore_errors=True);raise


def verify_backup(snapshot:Path)->dict:
    root=Path(snapshot).resolve();manifest_path=root/"manifest.json";payload=root/"payload"
    try:manifest=json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError,UnicodeError,json.JSONDecodeError) as exc:raise BackupError("BACKUP_MANIFEST_INVALID") from exc
    if manifest.get("schema_version")!="quantum-local-backup-v1" or not isinstance(manifest.get("entries"),list):raise BackupError("BACKUP_MANIFEST_INVALID")
    expected=set()
    for row in manifest["entries"]:
        if not isinstance(row,list) or len(row)!=3:raise BackupError("BACKUP_MANIFEST_INVALID")
        relative,digest,size=row
        path=(payload/relative).resolve()
        try:path.relative_to(payload.resolve())
        except ValueError as exc:raise BackupError("BACKUP_PATH_INVALID") from exc
        if not path.is_file() or path.is_symlink():raise BackupError("BACKUP_FILE_MISSING")
        actual_digest,actual_size=_hash(path)
        if actual_digest!=digest or actual_size!=size:raise BackupError("BACKUP_INTEGRITY_FAILED")
        expected.add(path)
    if set(_files(payload))!=expected:raise BackupError("BACKUP_UNTRACKED_FILE")
    return manifest


def restore_backup(snapshot:Path,target_root:Path,*,encrypted_storage_attested:bool)->Path:
    if not encrypted_storage_attested:raise BackupError("ENCRYPTED_STORAGE_ATTESTATION_REQUIRED")
    verify_backup(snapshot)
    target=Path(target_root).resolve()
    if target.exists() and any(target.iterdir()):raise BackupError("RESTORE_TARGET_NOT_EMPTY")
    target.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=Path(tempfile.mkdtemp(prefix=".quantum-restore-",dir=target.parent))
    try:
        shutil.copytree(Path(snapshot)/"payload",temp,dirs_exist_ok=True,symlinks=False)
        if target.exists():target.rmdir()
        os.replace(temp,target);os.chmod(target,0o700)
        return target
    except Exception:
        shutil.rmtree(temp,ignore_errors=True);raise
