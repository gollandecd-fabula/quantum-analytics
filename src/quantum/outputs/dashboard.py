from __future__ import annotations

from collections.abc import Mapping
import json
from typing import Any

from .dashboard_script_controls import DASHBOARD_JS_CONTROLS
from .dashboard_script_core import DASHBOARD_JS_CORE
from .dashboard_script_data import DASHBOARD_JS_DATA
from .dashboard_shell import DASHBOARD_BODY
from .dashboard_style import DASHBOARD_CSS
from .local_bundle import validate_local_output_bundle


INTERACTIVE_DASHBOARD_SCHEMA_VERSION = "quantum-interactive-dashboard-v2"


def _embedded_json(value: Any) -> str:
    return (
        json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        .replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def render_dashboard_html(bundle: Mapping[str, Any]) -> bytes:
    validate_local_output_bundle(bundle)
    payload = _embedded_json(bundle)
    document = """<!doctype html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="color-scheme" content="light">
<meta name="referrer" content="no-referrer">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'unsafe-inline'; img-src data:; connect-src 'none'; object-src 'none'; frame-src 'none'; base-uri 'none'; form-action 'none'">
<title>Quantum Analytics — локальный интерактивный отчёт</title>
<style>__DASHBOARD_CSS__</style>
</head>
<body data-dashboard-schema="__DASHBOARD_SCHEMA__">
__DASHBOARD_BODY__
<script id="bundle-data" type="application/json">__BUNDLE_DATA__</script>
<script>__DASHBOARD_JS__</script>
</body>
</html>"""
    document = (
        document.replace("__DASHBOARD_CSS__", DASHBOARD_CSS)
        .replace("__DASHBOARD_SCHEMA__", INTERACTIVE_DASHBOARD_SCHEMA_VERSION)
        .replace("__DASHBOARD_BODY__", DASHBOARD_BODY)
        .replace("__BUNDLE_DATA__", payload)
        .replace("__DASHBOARD_JS__", DASHBOARD_JS_CORE + DASHBOARD_JS_DATA + DASHBOARD_JS_CONTROLS)
    )
    return document.encode("utf-8")
