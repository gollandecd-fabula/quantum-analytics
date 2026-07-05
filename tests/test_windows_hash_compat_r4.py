from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
PILOT = ROOT / "src" / "quantum" / "pilot"
WINDOWS = ROOT / "scripts" / "windows"


class WindowsHashCompatR4Tests(unittest.TestCase):
    def test_hash_shim_implements_file_and_stream_sha256(self):
        script = (PILOT / "hash_compat.ps1").read_text(encoding="utf-8")
        self.assertIn("Get-Command -Name Get-FileHash", script)
        self.assertIn("System.Security.Cryptography.SHA256", script)
        self.assertIn('ParameterSetName = "LiteralPath"', script)
        self.assertIn('ParameterSetName = "InputStream"', script)
        self.assertIn("ComputeHash", script)

    def test_front_door_and_xlsx_helper_load_shim_before_hashing(self):
        for path in (
            WINDOWS / "import_source.ps1",
            PILOT / "import_xlsx_source.ps1",
        ):
            script = path.read_text(encoding="utf-8")
            load = script.index(". $hashCompat")
            first_hash = script.index("Get-FileHash", load)
            self.assertLess(load, first_hash, path.name)
            self.assertIn("Quantum SHA-256 compatibility shim was not found", script)

    def test_compatibility_scripts_are_ascii_for_windows_powershell(self):
        for path in (
            PILOT / "hash_compat.ps1",
            WINDOWS / "import_source.ps1",
            PILOT / "import_xlsx_source.ps1",
        ):
            payload = path.read_bytes()
            self.assertEqual(payload.decode("ascii").encode("ascii"), payload)


if __name__ == "__main__":
    unittest.main()
