from __future__ import annotations

from html.parser import HTMLParser
from pathlib import Path
import tempfile
import unittest

from quantum.outputs import (
    build_local_output_bundle,
    render_dashboard_html,
    verify_local_output_directory,
    write_local_output_bundle,
)
from quantum.outputs.dashboard import INTERACTIVE_DASHBOARD_SCHEMA_VERSION
from quantum.outputs.dashboard_script_controls import DASHBOARD_JS_CONTROLS
from quantum.outputs.dashboard_script_core import DASHBOARD_JS_CORE
from quantum.outputs.dashboard_script_data import DASHBOARD_JS_DATA
from tests.test_local_output_bundle_r1 import GENERATED_AT, report


DASHBOARD_JS = DASHBOARD_JS_CORE + DASHBOARD_JS_DATA + DASHBOARD_JS_CONTROLS


class _AuditParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.external_references: list[tuple[str, str, str]] = []
        self.csp = ""
        self.body_schema = ""

    def handle_starttag(self, tag: str, attrs):
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "meta" and values.get("http-equiv") == "Content-Security-Policy":
            self.csp = values.get("content", "")
        if tag == "body":
            self.body_schema = values.get("data-dashboard-schema", "")
        for field in ("src", "href"):
            value = values.get(field)
            if value and not value.startswith("#"):
                self.external_references.append((tag, field, value))


class InteractiveDashboardR1Tests(unittest.TestCase):
    def _bundle(self, payload=None):
        return build_local_output_bundle(payload or report(), generated_at=GENERATED_AT)

    def _html(self, payload=None) -> str:
        return render_dashboard_html(self._bundle(payload)).decode("utf-8")

    def test_dashboard_is_deterministic_offline_and_bundle_bound(self):
        bundle = self._bundle()
        first = render_dashboard_html(bundle)
        second = render_dashboard_html(bundle)
        self.assertEqual(first, second)
        html = first.decode("utf-8")
        self.assertIn(bundle["bundle_hash"], html)
        self.assertNotIn("http://", html)
        self.assertNotIn("https://", html)
        parser = _AuditParser()
        parser.feed(html)
        self.assertEqual(parser.external_references, [])
        self.assertEqual(parser.body_schema, INTERACTIVE_DASHBOARD_SCHEMA_VERSION)
        self.assertIn("connect-src 'none'", parser.csp)
        self.assertIn("object-src 'none'", parser.csp)
        self.assertIn("frame-src 'none'", parser.csp)
        self.assertIn("form-action 'none'", parser.csp)

    def test_dashboard_contains_required_interactive_contract(self):
        html = self._html()
        parser = _AuditParser()
        parser.feed(html)
        required_ids = {
            "bundle-data",
            "view-overview",
            "view-recommendations",
            "view-metrics",
            "view-quality",
            "financial-chart",
            "recommendation-grid",
            "metric-table-body",
            "quality-grid",
            "hash-grid",
            "detail-drawer",
            "rec-search",
            "severity",
            "priority",
            "category",
            "rec-sort",
            "rec-export",
            "metric-search",
            "metric-scope",
            "metric-state",
            "metric-unit",
            "metric-sort",
        }
        self.assertEqual(required_ids - parser.ids, set())
        self.assertIn("CSV защищён от внедрения формул электронных таблиц.", html)
        self.assertIn('aria-modal="true"', html)

    def test_source_content_is_escaped_and_dom_sinks_are_forbidden(self):
        payload = report()
        attack = "</script><img src=x onerror=globalThis.__quantumXss=1>"
        payload["limitations"].append(attack)
        html = self._html(payload)
        self.assertNotIn(attack, html)
        self.assertIn("\\u003c/script\\u003e", html)
        for token in (
            ".innerHTML",
            "document.write",
            "eval(",
            "fetch(",
            "XMLHttpRequest",
            "WebSocket",
            "EventSource",
            "sendBeacon",
        ):
            self.assertNotIn(token, DASHBOARD_JS)

    def test_csv_export_neutralizes_spreadsheet_formula_prefixes(self):
        self.assertIn("/^[=+\\-@]/", DASHBOARD_JS)
        self.assertIn('s="\'"+s', DASHBOARD_JS)
        self.assertIn("URL.createObjectURL", DASHBOARD_JS)
        self.assertNotIn("window.open", DASHBOARD_JS)

    def test_transactional_writer_verifies_interactive_dashboard(self):
        with tempfile.TemporaryDirectory() as directory:
            result = write_local_output_bundle(
                report(),
                output_root=Path(directory),
                generated_at=GENERATED_AT,
            )
            verified = verify_local_output_directory(Path(result["directory"]))
            self.assertEqual(verified["bundle_hash"], result["bundle_hash"])
            dashboard = Path(result["directory"]) / "dashboard.html"
            self.assertIn(
                f'data-dashboard-schema="{INTERACTIVE_DASHBOARD_SCHEMA_VERSION}"',
                dashboard.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
