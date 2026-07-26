from hashlib import sha256
import json
from pathlib import Path

workflow = Path('.github/workflows/quantum-universal-relaunch-r2.yml')
text = workflow.read_text(encoding='utf-8')
old = '''            $outputDirectory = [IO.Path]::GetFullPath(
              (Join-Path $env:QUR2_TARGET "output")
            )
'''
new = '''            $outputDirectory = [IO.Path]::GetFullPath(
              (Join-Path $env:LOCALAPPDATA "QuantumLocalProduction\\output")
            )
'''
if text.count(old) != 1:
    raise SystemExit(f'QUR2_OLD_OUTPUT_ROOT_COUNT={text.count(old)}')
workflow.write_text(text.replace(old, new, 1), encoding='utf-8', newline='\n')

overlay_path = Path('docs/evidence/ARTIFACT_MANIFEST_OVERLAY_QUANTUM_UNIVERSAL_RELAUNCH_R2.json')
overlay = json.loads(overlay_path.read_text(encoding='utf-8'))
payload = workflow.read_bytes()
entry = [workflow.as_posix(), sha256(payload).hexdigest(), len(payload)]
matches = 0
for index, current in enumerate(overlay['entries']):
    if current[0] == entry[0]:
        overlay['entries'][index] = entry
        matches += 1
if matches != 1:
    raise SystemExit(f'QUR2_MANIFEST_ENTRY_COUNT={matches}')
overlay_path.write_text(
    json.dumps(overlay, ensure_ascii=False, indent=2) + '\n',
    encoding='utf-8',
    newline='\n',
)
