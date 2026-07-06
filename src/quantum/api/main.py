from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlsplit

from quantum.api.local_pilot import local_pilot_health, render_local_ui


def technical_health() -> dict[str, Any]:
    return {
        "status": "ok",
        "component": "quantum-api",
        "mode": "foundation",
        "marketplace_write_enabled": False,
    }


class HealthHandler(BaseHTTPRequestHandler):
    server_version = "QuantumFoundation/0.0.1"

    def do_GET(self) -> None:
        parsed = urlsplit(self.path)
        if parsed.path == "/health/technical":
            self._json_response(HTTPStatus.OK, technical_health())
            return
        if parsed.path in {"/", "/local-pilot"}:
            self._bytes_response(HTTPStatus.OK, render_local_ui().encode("utf-8"), "text/html; charset=utf-8")
            return
        if parsed.path == "/api/local-pilot/health":
            self._json_response(HTTPStatus.OK, local_pilot_health())
            return
        self._json_response(HTTPStatus.NOT_FOUND, {"status": "not_found", "path": parsed.path})

    def log_message(self, format: str, *args: object) -> None:
        return

    def _json_response(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self._bytes_response(status, body, "application/json")

    def _bytes_response(self, status: HTTPStatus, body: bytes, content_type: str) -> None:
        self.send_response(status.value)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


def main() -> None:
    parser = argparse.ArgumentParser(description="Quantum API foundation runtime")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    args = parser.parse_args()
    server = ThreadingHTTPServer((args.host, args.port), HealthHandler)
    server.serve_forever()


if __name__ == "__main__":
    main()
