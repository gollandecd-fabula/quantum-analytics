from __future__ import annotations

import argparse
import base64
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from typing import Any

from quantum.finance import FinanceError
from quantum.ingestion import ReceiptError,StorageError

from .admission import AdmissionError
from .backup import BackupError,create_backup
from .financial_csv import FinancialCsvError
from .runtime import LocalPilotError
from .runtime_tenant import LocalPilotRuntime

_HOST="127.0.0.1"
_MAX_BODY=64*1024*1024
_INDEX="""<!doctype html><html lang=ru><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>Quantum Local Pilot</title><style>body{font-family:system-ui;max-width:960px;margin:2rem auto;padding:0 1rem}textarea,input,button{font:inherit;margin:.3rem 0;padding:.5rem}textarea{width:100%;min-height:9rem}pre{white-space:pre-wrap;background:#f4f4f4;padding:1rem}fieldset{margin:1rem 0}</style><h1>Quantum Local Pilot</h1><p>Локальный read-only контур. Данные не отправляются наружу.</p><fieldset><legend>1. Загрузка CSV</legend><input id=f type=file accept=.csv><button onclick=upload()>Загрузить</button></fieldset><fieldset><legend>2. Dataset ID</legend><input id=id size=48><button onclick=admit()>Допустить</button><button onclick=revoke()>Отозвать</button></fieldset><fieldset><legend>3. Профили товаров JSON</legend><textarea id=p>{"sku-1":{"cost_per_unit":"400","tax_rate":"0.06","other_expense_per_unit":"40"}}</textarea><input id=s placeholder='scenario_id — пусто для ACTUAL'><button onclick=calc()>Рассчитать</button></fieldset><button onclick=list()>Список datasets</button><pre id=o></pre><script>const out=x=>o.textContent=JSON.stringify(x,null,2);async function api(path,data){let r=await fetch(path,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(data)});out(await r.json())}async function upload(){let x=f.files[0];if(!x)return;let b=new Uint8Array(await x.arrayBuffer()),s='';for(let i=0;i<b.length;i+=32768)s+=String.fromCharCode(...b.slice(i,i+32768));await api('/api/upload',{filename:x.name,payload_base64:btoa(s)})}async function admit(){await api('/api/admit',{raw_file_id:id.value})}async function revoke(){await api('/api/revoke',{raw_file_id:id.value})}async function calc(){await api('/api/calculate',{raw_file_id:id.value,profiles:JSON.parse(p.value),scenario_id:s.value||null})}async function list(){let r=await fetch('/api/datasets');out(await r.json())}</script></html>"""


class LocalPilotHttpServer(ThreadingHTTPServer):
    daemon_threads=True
    allow_reuse_address=False
    def __init__(self,address:tuple[str,int],runtime:LocalPilotRuntime,backup_root:Path)->None:
        if address[0]!=_HOST:raise LocalPilotError("LOCALHOST_BIND_REQUIRED")
        self.runtime=runtime;self.backup_root=backup_root
        super().__init__(address,LocalPilotHandler)


class LocalPilotHandler(BaseHTTPRequestHandler):
    server:LocalPilotHttpServer

    def log_message(self,format:str,*args:object)->None:
        return

    def _headers(self,status:int,content_type:str)->None:
        self.send_response(status)
        self.send_header("Content-Type",content_type)
        self.send_header("Cache-Control","no-store")
        self.send_header("X-Content-Type-Options","nosniff")
        self.send_header("Referrer-Policy","no-referrer")
        self.send_header("Content-Security-Policy","default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers()

    def _json(self,status:int,payload:Any)->None:
        body=json.dumps(payload,ensure_ascii=False,separators=(",",":")).encode()
        self._headers(status,"application/json; charset=utf-8");self.wfile.write(body)

    def _body(self)->dict[str,Any]:
        try:length=int(self.headers.get("Content-Length","0"))
        except ValueError as exc:raise LocalPilotError("REQUEST_LENGTH_INVALID") from exc
        if length<=0 or length>_MAX_BODY:raise LocalPilotError("REQUEST_SIZE_INVALID")
        try:value=json.loads(self.rfile.read(length).decode("utf-8"))
        except (UnicodeError,json.JSONDecodeError) as exc:raise LocalPilotError("REQUEST_JSON_INVALID") from exc
        if not isinstance(value,dict):raise LocalPilotError("REQUEST_JSON_INVALID")
        return value

    def do_GET(self)->None:
        try:
            if self.path=="/":
                self._headers(HTTPStatus.OK,"text/html; charset=utf-8");self.wfile.write(_INDEX.encode());return
            if self.path=="/api/health":self._json(HTTPStatus.OK,{"status":"ok","host":_HOST,"mode":"LOCAL_PILOT","marketplace_writes":False});return
            if self.path=="/api/datasets":self._json(HTTPStatus.OK,{"datasets":self.server.runtime.datasets()});return
            self._json(HTTPStatus.NOT_FOUND,{"error":"NOT_FOUND"})
        except Exception as exc:self._error(exc)

    def do_POST(self)->None:
        try:
            data=self._body();runtime=self.server.runtime
            if self.path=="/api/upload":
                filename=data.get("filename");encoded=data.get("payload_base64")
                if not isinstance(filename,str) or not isinstance(encoded,str):raise LocalPilotError("UPLOAD_REQUEST_INVALID")
                try:payload=base64.b64decode(encoded,validate=True)
                except ValueError as exc:raise LocalPilotError("UPLOAD_BASE64_INVALID") from exc
                self._json(HTTPStatus.OK,runtime.upload(filename,payload));return
            raw_file_id=data.get("raw_file_id")
            if not isinstance(raw_file_id,str) or not raw_file_id:raise LocalPilotError("RAW_FILE_ID_REQUIRED")
            if self.path=="/api/admit":self._json(HTTPStatus.OK,runtime.admit(raw_file_id));return
            if self.path=="/api/revoke":self._json(HTTPStatus.OK,runtime.revoke(raw_file_id));return
            if self.path=="/api/calculate":
                profiles=data.get("profiles");scenario_id=data.get("scenario_id")
                if not isinstance(profiles,dict) or (scenario_id is not None and not isinstance(scenario_id,str)):raise LocalPilotError("CALCULATION_REQUEST_INVALID")
                self._json(HTTPStatus.OK,runtime.calculate_dataset(raw_file_id,profiles,scenario_id=scenario_id));return
            if self.path=="/api/backup":
                snapshot=create_backup(runtime.root,self.server.backup_root,encrypted_storage_attested=runtime.encrypted_storage_attested)
                self._json(HTTPStatus.OK,{"snapshot":snapshot.name});return
            self._json(HTTPStatus.NOT_FOUND,{"error":"NOT_FOUND"})
        except Exception as exc:self._error(exc)

    def _error(self,exc:Exception)->None:
        allowed=(LocalPilotError,AdmissionError,BackupError,FinancialCsvError,FinanceError,ReceiptError,StorageError)
        code=getattr(exc,"code","INTERNAL_ERROR") if isinstance(exc,allowed) else "INTERNAL_ERROR"
        status=HTTPStatus.BAD_REQUEST if code!="INTERNAL_ERROR" else HTTPStatus.INTERNAL_SERVER_ERROR
        self._json(status,{"error":code})


def build_server(data_dir:Path,*,port:int=8765,encrypted_storage_attested:bool=False,tenant_id:str="local-org",account_id:str="local-operator")->LocalPilotHttpServer:
    if not isinstance(port,int) or not 0<=port<=65535:raise LocalPilotError("PORT_INVALID")
    runtime=LocalPilotRuntime(data_dir,tenant_id=tenant_id,account_id=account_id,encrypted_storage_attested=encrypted_storage_attested)
    return LocalPilotHttpServer((_HOST,port),runtime,data_dir/"backups")


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(prog="quantum-local-pilot")
    parser.add_argument("--data-dir",type=Path,default=Path(".quantum-local"))
    parser.add_argument("--port",type=int,default=8765)
    parser.add_argument("--encrypted-storage-attested",action="store_true")
    args=parser.parse_args(argv)
    server=build_server(args.data_dir,port=args.port,encrypted_storage_attested=args.encrypted_storage_attested)
    print(f"Quantum Local Pilot: http://{_HOST}:{server.server_address[1]}")
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
    return 0


if __name__=="__main__":raise SystemExit(main())
