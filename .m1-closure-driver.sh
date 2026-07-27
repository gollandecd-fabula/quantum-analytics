#!/usr/bin/env bash
set -euo pipefail
BASE_SHA=bbdf8b14ccfb8480304549943d418abb0254386c
BASE_TREE_SHA=d593b6c9f801110135f1f303ce1b6a4b00e95abc
PAYLOAD_BASE64_SHA256=da81e4f1a08127332db9fffa858b19956a7827547b0dd696e4129d9724875b57
PAYLOAD_BASE64_SIZE=20352
ARCHIVE_SHA256=8858220d781fea68dba454d24ab671f6cf8c03b1ed9ac9c6493b96d2a9293ce8
ARCHIVE_SIZE=15262
EXPECTED_TREE_SHA=6cd0a8974965a6eb66886e740a901c960b3b3a2a
CANDIDATE_BRANCH=tmp/m1-gate-candidate
EVIDENCE="$RUNNER_TEMP/m1-gate-closure"
mkdir -p "$EVIDENCE"
cat .m1-closure-payload/chunk.* > "$RUNNER_TEMP/payload.b64"
test "$(wc -c < "$RUNNER_TEMP/payload.b64")" -eq "$PAYLOAD_BASE64_SIZE"
echo "$PAYLOAD_BASE64_SHA256  $RUNNER_TEMP/payload.b64" | sha256sum --check
base64 --decode "$RUNNER_TEMP/payload.b64" > "$RUNNER_TEMP/m1-closure.tar.gz"
test "$(wc -c < "$RUNNER_TEMP/m1-closure.tar.gz")" -eq "$ARCHIVE_SIZE"
echo "$ARCHIVE_SHA256  $RUNNER_TEMP/m1-closure.tar.gz" | sha256sum --check
git checkout --detach "$BASE_SHA"
test "$(git rev-parse HEAD)" = "$BASE_SHA"
test "$(git rev-parse 'HEAD^{tree}')" = "$BASE_TREE_SHA"
test -z "$(git status --porcelain)"
tar -xzf "$RUNNER_TEMP/m1-closure.tar.gz"
git diff --check
git add -A
cat > "$EVIDENCE/expected-paths.txt" <<'PATHS'
docs/evidence/ARTIFACT_MANIFEST_OVERLAY_AGENT_V3_1_M1.json
docs/evidence/agent_v3_1/AUTONOMOUS_EXECUTION_STATE_M1_RUNTIME.json
docs/evidence/agent_v3_1/CLAIM_LEDGER.json
docs/evidence/agent_v3_1/DEFECT_REGISTER.json
docs/evidence/agent_v3_1/M1_EVIDENCE_INGESTION_ATTEMPT_001_FAILURE.json
docs/evidence/agent_v3_1/M1_IMPLEMENTATION_REPORT.json
docs/evidence/agent_v3_1/M1_LITERAL_RTM_INGESTION_REPORT.json
docs/evidence/agent_v3_1/M1_NEGATIVE_CONTROL_REPORT.json
docs/evidence/agent_v3_1/M1_SCHEDULER_DECISION.json
docs/evidence/agent_v3_1/M1_SIGNED_WORK_ORDER.json
docs/evidence/agent_v3_1/ROLE_PERMISSION_POLICY.json
docs/evidence/agent_v3_1/ROLE_TRACE_INDEX.json
docs/evidence/agent_v3_1/STATE_TRANSITION_COVERAGE.json
docs/evidence/agent_v3_1/WORK_ORDER_LEDGER_M1_RUNTIME.json
docs/evidence/agent_v3_1/WORK_ORDER_M1_EVIDENCE_MANIFEST_CORRECTIVE_001.json
tests/integration_manifest_support_m8.py
tests/test_agent_v3_1_m0_r7_remote_closure.py
tests/test_agent_v3_1_m1_opening.py
tests/test_wbr2_m5_closure.py
tests/test_wbr2_m5_closure_corrective_r2.py
PATHS
LC_ALL=C sort -o "$EVIDENCE/expected-paths.txt" "$EVIDENCE/expected-paths.txt"
git diff --cached --name-only | LC_ALL=C sort > "$EVIDENCE/actual-paths.txt"
diff -u "$EVIDENCE/expected-paths.txt" "$EVIDENCE/actual-paths.txt" | tee "$EVIDENCE/scope-diff.txt"
test "$(wc -l < "$EVIDENCE/actual-paths.txt")" -eq 20
if grep -E '^(src/|scripts/windows/|requirements/|installer/)' "$EVIDENCE/actual-paths.txt"; then
  echo M1_GATE_PRODUCT_SCOPE_VIOLATION >&2
  exit 1
fi
export PYTHONPATH="$GITHUB_WORKSPACE/src"
python -m unittest -v \
  tests.test_m9_maximum_assurance_control_plane \
  tests.test_m9_literal_rtm_control_plane \
  tests.test_agent_v3_1_m1_opening \
  tests.test_agent_v3_1_m0_r7_remote_closure \
  tests.test_wbr2_m5_closure \
  tests.test_wbr2_m5_closure_corrective_r2 \
  tests.test_a0_manifest_diagnostic.ManifestDiagnosticTests.test_manifest_diff_is_empty \
  tests.test_b1a_artifact_manifest.B1aArtifactManifestTests.test_manifest_matches_current_tracked_tree \
  2>&1 | tee "$EVIDENCE/targeted-governance-manifest.log"
python -m quantum.scripts.ci 2>&1 | tee "$EVIDENCE/full-source-ci.log"
git config user.name quantum-ci
git config user.email quantum-ci@users.noreply.github.com
git commit -m "Ingest M1 runtime evidence and close Gate M1 manifest"
test "$(git rev-parse 'HEAD^{tree}')" = "$EXPECTED_TREE_SHA"
git rev-parse HEAD | tee "$EVIDENCE/candidate.commit-sha"
git rev-parse 'HEAD^{tree}' | tee "$EVIDENCE/candidate.tree-sha"
git diff-tree --no-commit-id --name-status -r HEAD > "$EVIDENCE/candidate.name-status"
git push origin "HEAD:refs/heads/$CANDIDATE_BRANCH"
