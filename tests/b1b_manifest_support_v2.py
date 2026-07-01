from __future__ import annotations
import base64,hashlib,json,subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MANIFEST_PATH=ROOT/"docs/evidence/ARTIFACT_MANIFEST.json"
OVERLAYS=(
("ARTIFACT_MANIFEST_OVERLAY.json","base_manifest_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_B3_RUNTIME.json","base_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_B3_FINAL.json","base_runtime_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_OSS_ADMISSION.json","base_final_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_P1.json","base_oss_admission_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_P1_CLOSURE.json","base_p1_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_P13.json","base_p1_closure_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_P13_MERGE_GATE.json","base_p13_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_P13_CLOSURE.json","base_p13_merge_gate_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_P14.json","base_p13_closure_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_P14_CLOSURE.json","base_p14_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_P15.json","base_p14_closure_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_P15_CLOSURE.json","base_p15_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_RECOVERY_QCP_2026_07_01_R1.json","base_p15_closure_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_ASSURANCE_PLAN_2026_07_08.json","base_recovery_qcp_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_REAL_DATA_PILOT_2026_07_08.json","base_assurance_plan_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_B1B_RESCUE.json","base_real_data_pilot_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_B1B_RESCUE_V2.json","base_b1b_rescue_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_B1B_NEXT.json","base_b1b_rescue_v2_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_B1B_CONTROL.json","base_b1b_next_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_B1B_FINAL.json","base_b1b_control_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_B1B_R6.json","base_b1b_final_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_B1B_R7.json","base_b1b_r6_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_B1B_R8.json","base_b1b_r7_overlay_git_blob_sha"),
("ARTIFACT_MANIFEST_OVERLAY_B1B_R9.json","base_b1b_r8_overlay_git_blob_sha"),
)
CONTROL_PATHS={"docs/evidence/ARTIFACT_MANIFEST.json",*("docs/evidence/"+n for n,_ in OVERLAYS)}
ARTIFACT_FIELDS=["path","sha256","size_bytes"]
B1A_SCHEMAS={
"schemas/calculation-profile.schema.json",
"schemas/configuration-rule.schema.json",
"schemas/metric-definition.schema.json",
"schemas/rounding-policy.schema.json",
"schemas/rule-resolution-result.schema.json",
"schemas/safe-expression.schema.json",
}

def git_blob_sha(data:bytes)->str:
 return hashlib.sha1(f"blob {len(data)}\0".encode("ascii")+data).hexdigest()

def tracked_paths()->list[str]:
 out=subprocess.check_output(["git","ls-files","-z"],cwd=ROOT).decode()
 return sorted(p for p in out.split("\0") if p and p not in CONTROL_PATHS)

def apply_entries(artifacts:dict[str,list],overlay:dict)->None:
 encoding=overlay.get("hash_encoding","sha256-hex")
 for path,digest,size in overlay["entries"]:
  if encoding=="sha256-base64":digest=base64.b64decode(digest,validate=True).hex()
  elif encoding!="sha256-hex":raise AssertionError("ARTIFACT_MANIFEST_HASH_ENCODING_UNSUPPORTED")
  artifacts[path]=[path,digest,size]
 for path in overlay.get("remove_paths",[]):artifacts.pop(path,None)

def load_effective_manifest()->dict:
 base=MANIFEST_PATH.read_bytes();current=json.loads(base);artifacts={r[0]:r for r in current["artifacts"]};previous=base
 for name,field in OVERLAYS:
  raw=(ROOT/"docs/evidence"/name).read_bytes();overlay=json.loads(raw)
  if overlay[field]!=git_blob_sha(previous):raise AssertionError("ARTIFACT_MANIFEST_OVERLAY_BASE_MISMATCH:"+name)
  apply_entries(artifacts,overlay);previous=raw
 current["artifacts"]=[artifacts[p] for p in sorted(artifacts)]
 current["artifact_count"]=len(current["artifacts"])
 return current

def expected_manifest(current:dict)->dict:
 artifacts=[]
 for path in tracked_paths():
  data=(ROOT/path).read_bytes();artifacts.append([path,hashlib.sha256(data).hexdigest(),len(data)])
 return {"project":current["project"],"generated_on":"2026-06-27","package_version":"6","source_constitution_file":current["source_constitution_file"],"source_constitution_sha256":current["source_constitution_sha256"],"artifact_count":len(artifacts),"artifact_fields":ARTIFACT_FIELDS,"artifacts":artifacts}
