import unittest

from quantum.api.main import technical_health as api_health
from quantum.worker.main import run_once, technical_health as worker_health


class RuntimeHealthTests(unittest.TestCase):
    def test_api_is_read_only(self):
        self.assertFalse(api_health()["marketplace_write_enabled"])

    def test_worker_is_read_only(self):
        self.assertFalse(worker_health()["marketplace_write_enabled"])

    def test_worker_is_explicitly_idle_without_queue(self):
        result = run_once()
        self.assertEqual(result["status"], "idle")
        self.assertEqual(result["processed"], 0)


if __name__ == "__main__":
    unittest.main()
