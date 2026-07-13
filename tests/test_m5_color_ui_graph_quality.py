from __future__ import annotations

from html.parser import HTMLParser
import unittest

from quantum.outputs import build_local_output_bundle, render_dashboard_html
from quantum.outputs.dashboard import INTERACTIVE_DASHBOARD_SCHEMA_VERSION
from quantum.outputs.dashboard_script_controls import DASHBOARD_JS_CONTROLS
from quantum.outputs.dashboard_script_core import DASHBOARD_JS_CORE
from quantum.outputs.dashboard_script_data import DASHBOARD_JS_DATA
from quantum.outputs.dashboard_shell import DASHBOARD_BODY
from quantum.outputs.dashboard_style import DASHBOARD_CSS
from tests.test_local_output_bundle_r1 import GENERATED_AT, report


DASHBOARD_JS = DASHBOARD_JS_CORE + DASHBOARD_JS_DATA + DASHBOARD_JS_CONTROLS


class _Parser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ids: set[str] = set()
        self.external: list[tuple[str, str, str]] = []
        self.schema = ""

    def handle_starttag(self, tag: str, attrs) -> None:
        values = dict(attrs)
        if values.get("id"):
            self.ids.add(values["id"])
        if tag == "body":
            self.schema = values.get("data-dashboard-schema", "")
        for field in ("src", "href"):
            value = values.get(field)
            if value and not value.startswith("#"):
                self.external.append((tag, field, value))


class M5ColorUiGraphQualityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        bundle = build_local_output_bundle(report(), generated_at=GENERATED_AT)
        cls.first = render_dashboard_html(bundle)
        cls.second = render_dashboard_html(bundle)
        cls.html = cls.first.decode("utf-8")
        cls.parser = _Parser()
        cls.parser.feed(cls.html)

    def test_dashboard_v2_is_deterministic_offline_and_safe(self) -> None:
        self.assertEqual(self.first, self.second)
        self.assertEqual(
            INTERACTIVE_DASHBOARD_SCHEMA_VERSION,
            "quantum-interactive-dashboard-v2",
        )
        self.assertEqual(self.parser.schema, INTERACTIVE_DASHBOARD_SCHEMA_VERSION)
        self.assertEqual(self.parser.external, [])
        self.assertNotIn("http://", self.html)
        self.assertNotIn("https://", self.html)
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

    def test_decision_center_and_graph_contract_is_complete(self) -> None:
        required = {
            "decision-center",
            "decision-banner",
            "decision-banner-title",
            "decision-readiness",
            "decision-readiness-bar",
            "decision-readiness-checks",
            "financial-chart",
            "cost-composition-chart",
            "priority-chart",
            "history-chart",
            "priority-actions",
            "overview-status",
        }
        self.assertEqual(required - self.parser.ids, set())
        self.assertIn("Центр решений", DASHBOARD_BODY)
        self.assertIn("ПРИБЫЛЬ → УСТОЙЧИВЫЙ РОСТ → ОБОРОТ", DASHBOARD_BODY)
        self.assertIn("Quantum только рекомендует действия", DASHBOARD_BODY)

    def test_financial_graph_has_shared_zero_axis_and_signed_expenses(self) -> None:
        self.assertIn("chart-zero", DASHBOARD_JS_CORE)
        self.assertIn("chart-fill-${direction}", DASHBOARD_JS_CORE)
        self.assertIn(".chart-fill-negative", DASHBOARD_CSS)
        self.assertIn(".chart-fill-positive", DASHBOARD_CSS)
        self.assertIn("item.type==='expense'?-Math.abs(item.value):item.value", DASHBOARD_JS_CORE)
        self.assertIn("signedMoney(item.signed)", DASHBOARD_JS_CORE)
        self.assertIn("Доходы расположены справа от нуля, расходы — слева", DASHBOARD_BODY)
        self.assertIn("role','img'", DASHBOARD_JS_CORE)

    def test_cost_and_priority_graphs_are_data_bound_not_decorative(self) -> None:
        self.assertIn("conic-gradient", DASHBOARD_JS_CORE)
        self.assertIn("costs.reduce", DASHBOARD_JS_CORE)
        self.assertIn("item.value/total*100", DASHBOARD_JS_CORE)
        self.assertIn("RECOMMENDATIONS.filter", DASHBOARD_JS_CORE)
        for token in ("--chart-1", "--chart-3", "--chart-6", "--chart-9"):
            self.assertIn(token, DASHBOARD_CSS)
        self.assertIn("Доход +", DASHBOARD_BODY)
        self.assertIn("Расход −", DASHBOARD_BODY)

    def test_missing_history_is_fail_closed_and_never_fabricated(self) -> None:
        self.assertIn("points.length<2", DASHBOARD_JS_CORE)
        self.assertIn("Недостаточно исторических данных", DASHBOARD_JS_CORE)
        self.assertIn("NO_HISTORICAL_SERIES", DASHBOARD_JS_CORE)
        self.assertIn("не строит фиктивный тренд", DASHBOARD_JS_CORE)
        self.assertNotIn("Math.random", DASHBOARD_JS)

    def test_accessibility_responsive_and_long_text_controls_are_present(self) -> None:
        self.assertIn('role="meter"', DASHBOARD_BODY)
        self.assertIn('aria-valuemin="0"', DASHBOARD_BODY)
        self.assertIn("ArrowLeft", DASHBOARD_JS_CORE)
        self.assertIn("ArrowRight", DASHBOARD_JS_CORE)
        self.assertIn("prefers-reduced-motion", DASHBOARD_CSS)
        self.assertIn("prefers-contrast: more", DASHBOARD_CSS)
        self.assertIn("overflow-wrap: anywhere", DASHBOARD_CSS)
        self.assertIn("@media (max-width: 520px)", DASHBOARD_CSS)

    def test_zero_counts_remain_zero_instead_of_not_available(self) -> None:
        self.assertIn("label!==undefined&&label!==null&&label!==''", DASHBOARD_JS_CORE)
        self.assertIn("stateLabel(value)", DASHBOARD_JS_CORE)
        self.assertNotIn("label||value||'NOT_AVAILABLE'", DASHBOARD_JS_CORE)

    def test_marketplace_write_boundary_remains_visible_and_disabled(self) -> None:
        self.assertIn("Запись на маркетплейс: отключена", DASHBOARD_JS_CORE)
        self.assertIn("ТОЛЬКО ЧТЕНИЕ", DASHBOARD_BODY)
        self.assertNotIn("CONFIRM_AND_EXECUTE", DASHBOARD_JS)
        self.assertNotIn("marketplace_write_enabled=true", DASHBOARD_JS)


if __name__ == "__main__":
    unittest.main()
