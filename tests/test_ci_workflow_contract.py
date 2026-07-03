import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
P16_BASE = "p16-real-xlsx-admission-r11-restored"


class CiWorkflowContractTests(unittest.TestCase):
    def workflow(self, name: str) -> str:
        return (ROOT / ".github" / "workflows" / name).read_text(
            encoding="utf-8"
        )

    def test_foundation_ci_uses_exact_pull_request_head(self):
        workflow = self.workflow("foundation-ci.yml")
        self.assertIn(
            "TARGET_SHA: ${{ github.event.pull_request.head.sha || github.sha }}",
            workflow,
        )
        self.assertIn('git fetch --depth=1 origin "${TARGET_SHA}"', workflow)
        self.assertIn('test "$(git rev-parse HEAD)" = "${TARGET_SHA}"', workflow)
        self.assertNotIn('git fetch --depth=1 origin "${GITHUB_SHA}"', workflow)

    def test_stacked_p16_base_is_enabled_for_both_workflows(self):
        for name in ("foundation-ci.yml", "oss-admission-ci.yml"):
            with self.subTest(name=name):
                workflow = self.workflow(name)
                self.assertIn(f"      - {P16_BASE}", workflow)
                self.assertIn("  workflow_dispatch:", workflow)


if __name__ == "__main__":
    unittest.main()
