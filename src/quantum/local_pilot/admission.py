from __future__ import annotations

import json
import os
import tempfile
from dataclasses import asdict,dataclass
from datetime import datetime,timezone
from enum import Enum
from pathlib import Path
from threading import RLock

from quantum.access import TenantContext
from quantum.ingestion.storage import RawFileRecord,RawFileState


class AdmissionError(ValueError):
    def __init__(self,code:str)->None:
        super().__init__(code);self.code=code


class DatasetState(str,Enum):
    DECLARED="DECLARED"
    QUARANTINED="QUARANTINED"
    VALIDATED="VALIDATED"
    ADMITTED="ADMITTED"
    REJECTED="REJECTED"
    REVOKED="REVOKED"


@dataclass(frozen=True,slots=True)
class DatasetRecord:
    raw_file_id:str
    tenant_id:str
    sha256:str
    state:str
    schema_id:str|None
    diagnostics:tuple[str,...]
    updated_at:str
    actor:str|None


class AdmissionLedger:
    def __init__(self,path:Path)->None:
        self._path=Path(path);self._lock=RLock()
        self._path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
        if not self._path.exists():self._write({"version":1,"records":{}})

    @staticmethod
    def _now()->str:
        return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00","Z")

    @staticmethod
    def _check_tenant(tenant:TenantContext)->None:
        if not isinstance(tenant,TenantContext):raise AdmissionError("TENANT_CONTEXT_REQUIRED")

    def _load(self)->dict:
        try:
            data=json.loads(self._path.read_text(encoding="utf-8"))
            if data.get("version")!=1 or not isinstance(data.get("records"),dict):raise ValueError
            return data
        except (OSError,UnicodeError,json.JSONDecodeError,ValueError) as exc:
            raise AdmissionError("ADMISSION_LEDGER_INVALID") from exc

    def _write(self,data:dict)->None:
        payload=json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(",",":")).encode()
        with tempfile.NamedTemporaryFile(dir=self._path.parent,delete=False) as handle:
            temp=Path(handle.name)
            try:
                handle.write(payload);handle.flush();os.fsync(handle.fileno())
                os.replace(temp,self._path)
                fd=os.open(self._path.parent,os.O_RDONLY)
                try:os.fsync(fd)
                finally:os.close(fd)
            except Exception:
                temp.unlink(missing_ok=True);raise

    @staticmethod
    def _decode(value:dict)->DatasetRecord:
        try:
            return DatasetRecord(
                raw_file_id=str(value["raw_file_id"]),tenant_id=str(value["tenant_id"]),
                sha256=str(value["sha256"]),state=DatasetState(value["state"]).value,
                schema_id=value.get("schema_id"),diagnostics=tuple(value.get("diagnostics",[])),
                updated_at=str(value["updated_at"]),actor=value.get("actor"),
            )
        except (KeyError,TypeError,ValueError) as exc:
            raise AdmissionError("ADMISSION_LEDGER_INVALID") from exc

    def _put(self,data:dict,record:DatasetRecord)->DatasetRecord:
        data["records"][record.raw_file_id]=asdict(record)|{"diagnostics":list(record.diagnostics)}
        self._write(data);return record

    def declare(self,tenant:TenantContext,raw:RawFileRecord)->DatasetRecord:
        self._check_tenant(tenant)
        if not isinstance(raw,RawFileRecord) or raw.tenant_id!=tenant.tenant_id:raise AdmissionError("DATASET_NOT_FOUND")
        with self._lock:
            data=self._load();existing=data["records"].get(raw.raw_file_id)
            if existing:
                record=self._decode(existing)
                if record.tenant_id!=tenant.tenant_id or record.sha256!=raw.sha256:raise AdmissionError("ADMISSION_CONFLICT")
                return record
            return self._put(data,DatasetRecord(raw.raw_file_id,tenant.tenant_id,raw.sha256,DatasetState.DECLARED.value,None,(),self._now(),None))

    def record_validation(self,tenant:TenantContext,raw:RawFileRecord)->DatasetRecord:
        self._check_tenant(tenant)
        mapping={RawFileState.VALID:DatasetState.VALIDATED,RawFileState.QUARANTINED:DatasetState.QUARANTINED,RawFileState.REJECTED:DatasetState.REJECTED}
        if raw.state not in mapping:raise AdmissionError("DATASET_NOT_VALIDATED")
        with self._lock:
            data=self._load();current=self._decode(data["records"].get(raw.raw_file_id,{}))
            if current.tenant_id!=tenant.tenant_id or current.sha256!=raw.sha256:raise AdmissionError("DATASET_NOT_FOUND")
            if current.state in {DatasetState.ADMITTED.value,DatasetState.REVOKED.value}:return current
            record=DatasetRecord(raw.raw_file_id,tenant.tenant_id,raw.sha256,mapping[raw.state].value,raw.schema_id,tuple(raw.diagnostics),self._now(),None)
            return self._put(data,record)

    def get(self,tenant:TenantContext,raw_file_id:str)->DatasetRecord:
        self._check_tenant(tenant)
        with self._lock:
            item=self._load()["records"].get(raw_file_id)
        if not item:raise AdmissionError("DATASET_NOT_FOUND")
        record=self._decode(item)
        if record.tenant_id!=tenant.tenant_id:raise AdmissionError("DATASET_NOT_FOUND")
        return record

    def admit(self,tenant:TenantContext,raw_file_id:str,actor:str)->DatasetRecord:
        if not isinstance(actor,str) or not actor:raise AdmissionError("ACTOR_REQUIRED")
        with self._lock:
            data=self._load();record=self.get(tenant,raw_file_id)
            if record.state==DatasetState.ADMITTED.value:return record
            if record.state!=DatasetState.VALIDATED.value:raise AdmissionError("DATASET_NOT_ADMISSIBLE")
            return self._put(data,DatasetRecord(record.raw_file_id,record.tenant_id,record.sha256,DatasetState.ADMITTED.value,record.schema_id,record.diagnostics,self._now(),actor))

    def revoke(self,tenant:TenantContext,raw_file_id:str,actor:str)->DatasetRecord:
        if not isinstance(actor,str) or not actor:raise AdmissionError("ACTOR_REQUIRED")
        with self._lock:
            data=self._load();record=self.get(tenant,raw_file_id)
            if record.state==DatasetState.REVOKED.value:return record
            if record.state not in {DatasetState.VALIDATED.value,DatasetState.ADMITTED.value}:raise AdmissionError("DATASET_NOT_REVOCABLE")
            return self._put(data,DatasetRecord(record.raw_file_id,record.tenant_id,record.sha256,DatasetState.REVOKED.value,record.schema_id,record.diagnostics,self._now(),actor))

    def require_admitted(self,tenant:TenantContext,raw_file_id:str)->DatasetRecord:
        record=self.get(tenant,raw_file_id)
        if record.state!=DatasetState.ADMITTED.value:raise AdmissionError("DATASET_NOT_ADMITTED")
        return record

    def list(self,tenant:TenantContext)->tuple[DatasetRecord,...]:
        self._check_tenant(tenant)
        with self._lock:data=self._load()
        return tuple(sorted((self._decode(v) for v in data["records"].values() if v.get("tenant_id")==tenant.tenant_id),key=lambda r:r.updated_at))
