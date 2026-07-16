import base64
import json
import sys
import tempfile
import unicodedata
import unittest
from dataclasses import asdict
from hashlib import sha256
from io import StringIO
from pathlib import Path
from unittest import mock

from quantum.pilot.windows_runner import main
from tests.p16_fixtures import build_xlsx, policy


class ReviewedFileHashTests(unittest.TestCase):
    def _case(self):
        temporary = tempfile.TemporaryDirectory()
        root = Path(temporary.name)
        workbook = build_xlsx(
            headers=("Артикул", "Количество продаж", "Сумма продаж"),
        )
        source = root / "report.xlsx"
        source.write_bytes(workbook)
        config = {
            "inspection_policy": json.loads(json.dumps(asdict(policy()))),
        }
        config_path = root / "config.json"
        config_path.write_text(json.dumps(config), encoding="utf-8")
        return temporary, root, source, config_path, workbook

    def test_matching_reviewed_hash_allows_schema_preview(self):
        temporary, root, source, config_path, workbook = self._case()
        self.addCleanup(temporary.cleanup)
        output = root / "preview.json"
        argv = [
            "windows_runner",
            "--file",
            str(source),
            "--config",
            str(config_path),
            "--storage-root",
            str(root / "storage"),
            "--output",
            str(output),
            "--home-local",
            "--discover-only",
            "--expected-file-sha256",
            sha256(workbook).hexdigest(),
            "--authority-attested",
        ]
        with mock.patch.object(sys, "argv", argv):
            self.assertEqual(main(), 0)
        preview = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(preview["file_sha256"], sha256(workbook).hexdigest())

    def test_mismatched_reviewed_hash_fails_closed(self):
        temporary, root, source, config_path, _ = self._case()
        self.addCleanup(temporary.cleanup)
        output = root / "preview.json"
        argv = [
            "windows_runner",
            "--file",
            str(source),
            "--config",
            str(config_path),
            "--storage-root",
            str(root / "storage"),
            "--output",
            str(output),
            "--home-local",
            "--discover-only",
            "--expected-file-sha256",
            "f" * 64,
            "--authority-attested",
            "--debug-errors",
        ]
        stderr = StringIO()
        with mock.patch.object(sys, "argv", argv), mock.patch.object(
            sys, "stderr", stderr
        ):
            self.assertEqual(main(), 2)
        self.assertFalse(output.exists())
        error = json.loads(stderr.getvalue())
        self.assertEqual(error["code"], "HOME_LOCAL_SOURCE_FILE_HASH_MISMATCH")


class ConfiguratorPrivacyTokenTests(unittest.TestCase):
    def test_generated_privacy_tokens_are_normalized_unique(self):
        repository_root = Path(__file__).resolve().parents[1]
        script = (
            repository_root / "scripts" / "windows" / "configure_home_local.ps1"
        ).read_text(encoding="ascii")

        plain_tokens = [
            "email",
            "phone",
            "telephone",
            "mobile",
            "address",
            "full name",
            "surname",
            "passport",
            "snils",
            "inn",
        ]
        encoded_tokens = [
            "0Y3Qu9C10LrRgtGA0L7QvdC90LDRjyDQv9C+0YfRgtCw",
            "0YLQtdC70LXRhNC+0L0=",
            "0LDQtNGA0LXRgQ==",
            "0YTQuNC+",
            "0YTQsNC80LjQu9C40Y8=",
            "0L/QsNGB0L/QvtGA0YI=",
            "0YHQvdC40LvRgQ==",
            "0LjQvdC9",
        ]
        self.assertNotIn('"e-mail"', script)
        for token in plain_tokens:
            self.assertIn(f'"{token}"', script)
        decoded_tokens = []
        for encoded in encoded_tokens:
            self.assertIn(encoded, script)
            decoded_tokens.append(base64.b64decode(encoded).decode("utf-8"))

        normalized = [
            "".join(
                character
                for character in unicodedata.normalize("NFKC", token).casefold()
                if character.isalnum()
            )
            for token in plain_tokens + decoded_tokens
        ]
        self.assertTrue(all(normalized))
        self.assertEqual(len(normalized), len(set(normalized)))


if __name__ == "__main__":
    unittest.main()
