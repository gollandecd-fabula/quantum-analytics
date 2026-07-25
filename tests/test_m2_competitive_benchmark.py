from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
BENCHMARK = ROOT / "docs/research/M2_COMPETITIVE_BENCHMARK_2026_07_11.json"


class M2CompetitiveBenchmarkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.payload = json.loads(BENCHMARK.read_text(encoding="utf-8"))

    def test_scope_is_research_only_and_read_only(self) -> None:
        scope = self.payload["scope"]
        self.assertFalse(scope["implementation_performed"])
        self.assertFalse(scope["marketplace_writes_enabled"])
        self.assertFalse(scope["main_branch_modified"])

    def test_required_platform_counts_and_source_policy(self) -> None:
        platforms = self.payload["platforms"]
        self.assertEqual(13, len(platforms))
        self.assertEqual(7, sum(item["group"] == "global" for item in platforms))
        self.assertEqual(6, sum(item["group"] == "regional" for item in platforms))
        for item in platforms:
            self.assertTrue(item["official_source_url"].startswith("https://"))
            self.assertIn(item["evidence_tier"], {"HIGH", "MEDIUM", "LOW"})

    def test_weighted_score_is_reproducible(self) -> None:
        weights = {
            item["id"]: item["weight_percent"]
            for item in self.payload["methodology"]["criteria"]
        }
        self.assertEqual(100, sum(weights.values()))
        for platform in self.payload["platforms"]:
            scores = platform["criterion_scores_0_to_4"]
            weighted = platform["weighted_public_evidence_fit_0_to_100"]
            if scores is None:
                self.assertIsNone(weighted)
                continue
            self.assertEqual(set(weights), set(scores))
            self.assertTrue(all(value in range(5) for value in scores.values()))
            expected = round(
                sum(weights[key] * scores[key] / 4 for key in weights),
                1,
            )
            self.assertEqual(expected, weighted)

    def test_decision_matrix_is_complete_and_fail_closed(self) -> None:
        matrix = self.payload["decision_matrix"]
        dispositions = {item["disposition"] for item in matrix}
        self.assertEqual({"ADOPT", "ADAPT", "DEFER", "REJECT"}, dispositions)
        rejected = {item["pattern"] for item in matrix if item["disposition"] == "REJECT"}
        self.assertIn(
            "Automatic bids, prices, campaigns, replies or inventory execution",
            rejected,
        )
        self.assertIn("Opaque estimates or hidden financial defaults", rejected)

    def test_low_evidence_service_is_not_scored(self) -> None:
        stat4market = next(
            item for item in self.payload["platforms"]
            if item["name"] == "Stat4Market"
        )
        self.assertEqual("LOW", stat4market["evidence_tier"])
        self.assertIsNone(stat4market["criterion_scores_0_to_4"])
        self.assertIsNone(stat4market["weighted_public_evidence_fit_0_to_100"])


if __name__ == "__main__":
    unittest.main()
