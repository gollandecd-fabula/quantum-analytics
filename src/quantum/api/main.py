from __future__ import annotations

import argparse
import json
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any


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
        if self.path == "/health/technical":
            payload = technical_health()
            self._json_response(HTTPStatus.OK, payload)
            return
        self._json_response(
            HTTPStatus.NOT_FOUND,
            {"status": "not_found", "path": self.path},
        )

    def log_message(self, format: str, *args: object) -> None:
        # Foundation avoids request-body or credential logging.
        return

    def _json_response(self, status: HTTPStatus, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
        self.send_response(status.value)
        self.send_header("Content-Type", "application/json")
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
