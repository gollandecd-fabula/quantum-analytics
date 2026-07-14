import unittest
from typing import get_type_hints

from quantum.ingestion.admission import StorageControlEvidence
from quantum.ingestion._admission_contracts_v2 import (
    StorageControlEvidence as RetiredStorageControlEvidence,
)
from quantum.ingestion._admission_evidence_checks_v2 import (
    require_evidence_binding,
    require_evidence_times,
)


class P16StorageTypeConsistencyTests(unittest.TestCase):
    def test_evidence_helpers_resolve_the_v3_storage_contract(self):
        self.assertIsNot(StorageControlEvidence, RetiredStorageControlEvidence)
        for helper in (require_evidence_binding, require_evidence_times):
            with self.subTest(helper=helper.__name__):
                self.assertIs(
                    get_type_hints(helper)["storage_evidence"],
                    StorageControlEvidence,
                )


if __name__ == "__main__":
    unittest.main()
