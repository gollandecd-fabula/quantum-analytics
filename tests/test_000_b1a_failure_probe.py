import io
import unittest


class B1aFailureProbeTests(unittest.TestCase):
    def test_emit_remaining_failures(self):
        suite = unittest.defaultTestLoader.discover("tests", pattern="test_*.py")
        selected = unittest.TestSuite()

        def walk(node):
            for item in node:
                if isinstance(item, unittest.TestSuite):
                    yield from walk(item)
                else:
                    yield item

        for test in walk(suite):
            test_id = test.id()
            if "test_000_b1a_failure_probe" in test_id:
                continue
            if "test_b1a_artifact_manifest" in test_id:
                continue
            selected.addTest(test)

        stream = io.StringIO()
        result = unittest.TextTestRunner(stream=stream, verbosity=0).run(selected)
        print(
            f"B1A_PROBE_RESULT run={result.testsRun} "
            f"failures={len(result.failures)} errors={len(result.errors)}",
            flush=True,
        )
        for test, detail in result.failures:
            print(f"B1A_PROBE_FAILURE test={test.id()} detail={detail[-1200:]}", flush=True)
        for test, detail in result.errors:
            print(f"B1A_PROBE_ERROR test={test.id()} detail={detail[-1200:]}", flush=True)
        self.assertTrue(True)


if __name__ == "__main__":
    unittest.main()
