from pathlib import Path
import unittest


class M2RuntimeDependencyModernizationTests(unittest.TestCase):
    def test_runtime_and_tzdata_are_exactly_pinned(self) -> None:
        root = Path(__file__).resolve().parents[1]
        builder = (root / "scripts/windows/build_two_installer_bundles.ps1").read_text(encoding="utf-8")
        requirements = (root / "requirements/windows-home-local.txt").read_text(encoding="utf-8")
        self.assertIn('"3.13.14"', builder)
        self.assertIn('c54d9b9bbb8a36e6489363ddd01139707fd781d72f1f9e90c7ec65d0061368e0', builder)
        self.assertIn('Test-Python313', builder)
        self.assertIn('Python313', builder)
        self.assertIn('sys.version_info >= (3,13)', builder)
        self.assertIn('tzdata==2026.3', requirements)
        self.assertIn('dc096730c87af6cab1b171c9d532be840741ff5d459015e7f6947bd7d7e54931', requirements)

    def test_stale_runtime_pins_are_absent_from_active_contracts(self) -> None:
        root = Path(__file__).resolve().parents[1]
        active = "\n".join((root / path).read_text(encoding="utf-8") for path in (
            "scripts/windows/build_two_installer_bundles.ps1",
            "requirements/windows-home-local.txt",
        ))
        for stale in ("3.12.10", "Python312", "Test-Python312", "tzdata==2026.2"):
            self.assertNotIn(stale, active)

    def test_runtime_hash_tamper_is_fail_closed(self) -> None:
        root = Path(__file__).resolve().parents[1]
        builder = (root / "scripts/windows/build_two_installer_bundles.ps1").read_text(encoding="utf-8")
        self.assertIn('if ($pythonActualSha256 -ne $pythonExpectedSha256)', builder)
        self.assertIn('if ($pythonActualHash -ne $pythonExpectedHash)', builder)


if __name__ == "__main__":
    unittest.main()
