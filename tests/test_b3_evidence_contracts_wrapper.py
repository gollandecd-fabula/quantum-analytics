import unittest
from tests import test_b3_evidence_contracts as core

_original_diagnose = core.diagnose
_original_mutate = core.mutate


def strict_diagnose(graph):
    diagnostic = _original_diagnose(graph)
    if diagnostic is not None:
        return diagnostic
    for node in graph.get("nodes", []):
        if node.get("node_type") == "SOURCE_FILE":
            retained = node.get("metadata", {}).get("retained_bytes_sha256")
            artifact = node.get("artifact_ref", {}).get("content_hash")
            if retained != artifact:
                return "EVIDENCE_HASH_MISMATCH"
    return None


def strict_mutate(base, mutation):
    reduced = {k: v for k, v in mutation.items() if k != "source_file_retained_hash"}
    graph = _original_mutate(base, reduced)
    if "source_file_retained_hash" in mutation:
        source_file = next(
            node for node in graph["nodes"] if node.get("node_type") == "SOURCE_FILE"
        )
        source_file["metadata"]["retained_bytes_sha256"] = mutation["source_file_retained_hash"]
        graph["content_hash"] = core.canonical_graph_hash(graph)
    return graph


core.diagnose = strict_diagnose
core.mutate = strict_mutate


class B3SourceFileHashEquality(unittest.TestCase):
    def test_source_file_hash_matches_retained_bytes(self):
        data = core.j(core.V)
        source_file = next(
            node for node in data["valid_graph"]["nodes"] if node.get("node_type") == "SOURCE_FILE"
        )
        self.assertEqual(
            source_file["artifact_ref"]["content_hash"],
            source_file["metadata"]["retained_bytes_sha256"],
        )
        mismatch = strict_mutate(
            data["valid_graph"], {"source_file_retained_hash": "e" * 64}
        )
        self.assertEqual(strict_diagnose(mismatch), "EVIDENCE_HASH_MISMATCH")


if __name__ == "__main__":
    unittest.main()
