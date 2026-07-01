from __future__ import annotations
import base64,hashlib,json,subprocess,unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
M=ROOT/"docs/evidence/ARTIFACT_MANIFEST.json"
O=(("ARTIFACT_MANIFEST_OVERLAY.json","base_manifest_git_blob_sha"),("ARTIFACT_MANIFEST_OVERLAY_B3_RUNTIME.json","base_overlay_git_blob_sha"),("ARTIFACT_MANIFEST_OVERLAY_B3_FINAL.json","base_runtime_overlay_git_blob_sha"),("ARTIFACT_MANIFEST_OVERLAY_OSS_ADMISSION.json","base_final_overlay_git_blob_sha"),("ARTIFACT_MANIFEST_OVERLAY_P1.json","base_oss_admission_overlay_git_blob_sha"),("ARTIFACT_MANIFEST_OVERLAY_P1_CLOSURE.json","base_p1_overlay_git_blob_sha"),("ARTIFACT_MANIFEST_OVERLAY_P13.json","base_p1_closure_overlay_git_blob_sha"),("ARTIFACT_MANIFEST_OVERLAY_P13_MERGE_GATE.json","base_p13_overlay_git_blob_sha"),("ARTIFACT_MANIFEST_OVERLAY_P13_CLOSURE.json","base_p13_merge_gate_overlay_git_blob_sha"),("ARTIFACT_MANIFEST_OVERLAY_P14.json","base_p13_closure_overlay_git_blob_sha"),("ARTIFACT_MANIFEST_OVERLAY_P14_CLOSURE.json","base_p14_overlay_git_blob_sha"),("ARTIFACT_MANIFEST_OVERLAY_P15.json","base_p14_closure_overlay_git_blob_sha"),("ARTIFACT_MANIFEST_OVERLAY_P15_CLOSURE.json","base_p15_overlay_git_blob_sha"),("ARTIFACT_MANIFEST_OVERLAY_RECOVERY_QCP_2026_07_01_R1.json","base_p15_closure_overlay_git_blob_sha"),("ARTIFACT_MANIFEST_OVERLAY_ASSURANCE_PLAN_2026_07_08.json","base_recovery_qcp_overlay_git_blob_sha"),("ARTIFACT_MANIFEST_OVERLAY_REAL_DATA_PILOT_2026_07_08.json","base_assurance_plan_overlay_git_blob_sha"),("ARTIFACT_MANIFEST_OVERLAY_B1B_RESCUE.json","base_real_data_pilot_overlay_git_blob_sha"))
C={"docs/evidence/ARTIFACT_MANIFEST.json",*("docs/evidence/"+n for n,_ in O)}
F=["path","sha256","size_bytes"]
S={"schemas/calculation-profile.schema.json","schemas/configuration-rule.schema.json","schemas/metric-definition.schema.json","schemas/rounding-policy.schema.json","schemas/rule-resolution-result.schema.json","schemas/safe-expression.schema.json"}
def git_blob_sha(b:bytes)->str:return hashlib.sha1(f"blob {len(b)}\0".encode()+b).hexdigest()
def tracked_paths()->list[str]:
 o=subprocess.check_output(["git","ls-files","-z"],cwd=ROOT).decode();return sorted(p for p in o.split("\0") if p and p not in C)
def apply_entries(a:dict[str,list],x:dict)->None:
 e=x.get("hash_encoding","sha256-hex")
 for p,d,z in x["entries"]:
  if e=="sha256-base64":d=base64.b64decode(d,validate=True).hex()
  elif e!="sha256-hex":raise AssertionError("ARTIFACT_MANIFEST_HASH_ENCODING_UNSUPPORTED")
  a[p]=[p,d,z]
 for p in x.get("remove_paths",[]):a.pop(p,None)
def load_effective_manifest()->dict:
 b=M.read_bytes();c=json.loads(b);a={r[0]:r for r in c["artifacts"]};q=b
 for n,k in O:
  p=ROOT/"docs/evidence"/n;t=p.read_bytes();x=json.loads(t)
  if x[k]!=git_blob_sha(q):raise AssertionError("ARTIFACT_MANIFEST_OVERLAY_BASE_MISMATCH:"+n)
  apply_entries(a,x);q=t
 c["artifacts"]=[a[p] for p in sorted(a)];c["artifact_count"]=len(a);return c
def expected_manifest(c:dict)->dict:
 a=[]
 for p in tracked_paths():
  b=(ROOT/p).read_bytes();a.append([p,hashlib.sha256(b).hexdigest(),len(b)])
 return {"project":c["project"],"generated_on":"2026-06-27","package_version":"6","source_constitution_file":c["source_constitution_file"],"source_constitution_sha256":c["source_constitution_sha256"],"artifact_count":len(a),"artifact_fields":F,"artifacts":a}
class B1aArtifactManifestTests(unittest.TestCase):
 def test_manifest_matches_current_tracked_tree(self):
  c=load_effective_manifest();self.assertEqual(c,expected_manifest(c))
 def test_manifest_contains_all_b1a_schemas(self):
  c=load_effective_manifest();self.assertEqual(c["artifact_fields"],F);p={r[0] for r in c["artifacts"]};self.assertTrue(S.issubset(p),S-p)
if __name__=="__main__":unittest.main()
