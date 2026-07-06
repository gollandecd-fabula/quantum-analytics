from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlsplit

from quantum.api.local_pilot import (
    analyze_uploaded_report,
    calculate_unit,
    local_pilot_health,
    render_local_ui,
    save_analysis_export,
    save_cost_table,
    upload_local_file,
)


class LocalPilotHandler(BaseHTTPRequestHandler):
    server_version = "QuantumLocalPilot/0.0.1"

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path in {"/", "/local-pilot"}:
            self._bytes(HTTPStatus.OK, render_local_ui().encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/local-pilot/health":
            self._json(HTTPStatus.OK, local_pilot_health())
            return
        self._json(HTTPStatus.NOT_FOUND, {"status": "not_found", "path": parsed.path})

    def do_POST(self) -> None:
        parsed = urlsplit(self.path)
        try:
            size = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"status": "rejected", "reason": "invalid_content_length"})
            return
        if size > 20 * 1024 * 1024:
            self._json(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, {"status": "rejected", "reason": "upload_too_large"})
            return
        data = self.rfile.read(size)

        if parsed.path == "/api/local-pilot/upload":
            query = parse_qs(parsed.query)
            filename = self.headers.get("X-Quantum-Filename") or (query.get("filename") or ["upload.bin"])[0]
            code, payload = upload_local_file(filename, data, self.headers.get("Content-Type", ""))
            self._json(HTTPStatus(code), payload)
            return

        if parsed.path == "/api/local-pilot/cost-table":
            query = parse_qs(parsed.query)
            filename = self.headers.get("X-Quantum-Filename") or (query.get("filename") or ["cost-table.csv"])[0]
            code, payload = save_cost_table(filename, data, self.headers.get("Content-Type", ""))
            self._json(HTTPStatus(code), payload)
            return

        if parsed.path in {"/api/local-pilot/calculate", "/api/local-pilot/analyze", "/api/local-pilot/export"}:
            try:
                payload = json.loads(data.decode("utf-8"))
            except (UnicodeDecodeError, json.JSONDecodeError):
                self._json(HTTPStatus.BAD_REQUEST, {"status": "blocked", "reason": "invalid_json"})
                return
            if not isinstance(payload, dict):
                self._json(HTTPStatus.BAD_REQUEST, {"status": "blocked", "reason": "json_object_required"})
                return
            if parsed.path == "/api/local-pilot/calculate":
                code, result = calculate_unit(payload)
            elif parsed.path == "/api/local-pilot/analyze":
                sha256 = payload.get("sha256")
                if not isinstance(sha256, str) or not sha256:
                    self._json(HTTPStatus.BAD_REQUEST, {"status": "blocked", "reason": "missing:sha256"})
                    return
                code, result = analyze_uploaded_report(sha256, payload)
            else:
                code, result = save_analysis_export(payload)
            self._json(HTTPStatus(code), result)
            return

        self._json(HTTPStatus.NOT_FOUND, {"status": "not_found", "path": parsed.path})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        self._bytes(
            status,
            json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8"),
            "application/json; charset=utf-8",
        )

    def _bytes(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Quantum Local Pilot runtime")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    ThreadingHTTPServer((args.host, args.port), LocalPilotHandler).serve_forever()


if __name__ == "__main__":
    main()
