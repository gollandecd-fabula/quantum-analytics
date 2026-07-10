from __future__ import annotations

import os
import threading
import time
import webbrowser
from quantum.api.local_pilot_server import create_local_server


def main() -> None:
    host = "127.0.0.1"
    try:
        preferred_port = int(os.environ.get("QUANTUM_PORT", "8080"))
    except ValueError as exc:
        raise SystemExit("QUANTUM_PORT must be an integer") from exc
    server, actual_port = create_local_server(host, preferred_port)
    url = f"http://{host}:{actual_port}/local-pilot"

    def open_browser() -> None:
        if os.environ.get("QUANTUM_NO_BROWSER") == "1":
            return
        time.sleep(0.8)
        webbrowser.open(url)

    threading.Thread(target=open_browser, daemon=True).start()
    server.serve_forever()


if __name__ == "__main__":
    main()
