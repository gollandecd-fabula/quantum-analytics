from __future__ import annotations

import argparse
import errno
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


def validate_loopback_host(host: str) -> str:
    if host != "127.0.0.1":
        raise ValueError("loopback_host_required")
    return host


def parse_content_length(raw: str | None) -> int:
    try:
        size = int(raw or "0")
    except ValueError as exc:
        raise ValueError("invalid_content_length") from exc
    if size < 0:
        raise ValueError("invalid_content_length")
    return size


def create_local_server(
    host: str, preferred_port: int, *, attempts: int = 20
) -> tuple[ThreadingHTTPServer, int]:
    host = validate_loopback_host(host)
    if not 1 <= preferred_port <= 65535:
        raise ValueError("invalid_port")
    if attempts < 1:
        raise ValueError("invalid_port_attempts")

    last_error: OSError | None = None
    for offset in range(attempts):
        port = preferred_port + offset
        if port > 65535:
            break
        try:
            server = ThreadingHTTPServer((host, port), LocalPilotHandler)
            return server, int(server.server_address[1])
        except OSError as exc:
            if exc.errno not in {errno.EADDRINUSE, 10048}:
                raise
            last_error = exc
    if last_error is not None:
        raise OSError(errno.EADDRINUSE, "no_available_loopback_port") from last_error
    raise ValueError("no_valid_port_in_range")


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
            size = parse_content_length(self.headers.get("Content-Length"))
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
                code, result = save_analysis_export(payload.get("analysis_sha256"))
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
    try:
        server, actual_port = create_local_server(args.host, args.port)
    except (ValueError, OSError) as exc:
        parser.error(str(exc))
    print(f"Quantum local pilot listening on http://127.0.0.1:{actual_port}/local-pilot", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
