import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


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

    def test_all_pull_requests_are_checked(self):
        foundation = self.workflow("foundation-ci.yml")
        oss = self.workflow("oss-admission-ci.yml")
        self.assertIn("  pull_request:\n  push:", foundation)
        self.assertIn("  pull_request:\n  workflow_dispatch:", oss)
        self.assertIn("  workflow_dispatch:", foundation)


if __name__ == "__main__":
    unittest.main()
