from __future__ import annotations

import os
import threading
import time
import webbrowser
from http.server import ThreadingHTTPServer

from quantum.api.local_pilot_server import LocalPilotHandler


def main() -> None:
    host = os.environ.get("QUANTUM_HOST", "127.0.0.1")
    port = int(os.environ.get("QUANTUM_PORT", "8080"))
    url = f"http://{host}:{port}/local-pilot"
    server = ThreadingHTTPServer((host, port), LocalPilotHandler)

    def open_browser() -> None:
        if os.environ.get("QUANTUM_NO_BROWSER") == "1":
            return
        time.sleep(0.8)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
