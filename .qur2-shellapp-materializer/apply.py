from hashlib import sha256
import json
from pathlib import Path

workflow = Path('.github/workflows/quantum-universal-relaunch-r2.yml')
text = workflow.read_text(encoding='utf-8')
old = '''            $outputDirectory = Join-Path $env:QUR2_TARGET "output"
            $beforeOutputs = @(Get-ChildItem $outputDirectory -Filter "import_*.json" -File)
            foreach ($number in 1..20) {
              $stdout = Join-Path $env:RUNNER_TEMP "qur2-import-$number.stdout.txt"
              $stderr = Join-Path $env:RUNNER_TEMP "qur2-import-$number.stderr.txt"
              $importScript = Join-Path $env:QUR2_TARGET "scripts\\import_source.ps1"
              $storageRoot = Join-Path $env:QUR2_TARGET "data"
              & powershell.exe -NoProfile -ExecutionPolicy Bypass `
                -File $importScript `
                -File $csv `
                -StorageRoot $storageRoot `
                -NonInteractive -AuthorityAttested -SchemaReviewed `
                -SkipDefenderScan `
                1> $stdout 2> $stderr
              $importExitCode = $LASTEXITCODE
              "IMPORT=$number EXIT=$importExitCode" | Add-Content $trace
              if ($importExitCode -ne 0) { throw "Rapid import $number failed." }
            }
            $afterOutputs = @(Get-ChildItem $outputDirectory -Filter "import_*.json" -File)
            $created = $afterOutputs.Count - $beforeOutputs.Count
            "RAPID_OUTPUTS_CREATED=$created" | Add-Content $trace
            if ($created -ne 20) {
              throw "Rapid imports did not create twenty distinct results."
            }
            if (@($afterOutputs.Name | Sort-Object -Unique).Count -ne $afterOutputs.Count) {
              throw "Output filename collision detected."
            }
'''
new = '''            $outputDirectory = [IO.Path]::GetFullPath(
              (Join-Path $env:QUR2_TARGET "output")
            )
            $createdOutputPaths = @()
            foreach ($number in 1..20) {
              $stdout = Join-Path $env:RUNNER_TEMP "qur2-import-$number.stdout.txt"
              $stderr = Join-Path $env:RUNNER_TEMP "qur2-import-$number.stderr.txt"
              $importScript = Join-Path $env:QUR2_TARGET "scripts\\import_source.ps1"
              $storageRoot = Join-Path $env:QUR2_TARGET "data"
              & powershell.exe -NoProfile -ExecutionPolicy Bypass `
                -File $importScript `
                -File $csv `
                -StorageRoot $storageRoot `
                -NonInteractive -AuthorityAttested -SchemaReviewed `
                -SkipDefenderScan `
                1> $stdout 2> $stderr
              $importExitCode = $LASTEXITCODE
              "IMPORT=$number EXIT=$importExitCode" | Add-Content $trace
              if ($importExitCode -ne 0) { throw "Rapid import $number failed." }
              $stdoutText = Get-Content $stdout -Raw -Encoding UTF8
              $reportLine = @(
                $stdoutText -split "`r?`n" |
                  Where-Object { $_ -match '^Отчёт:\\s*' }
              ) | Select-Object -Last 1
              if ([string]::IsNullOrWhiteSpace([string]$reportLine)) {
                throw "Rapid import $number omitted its report path."
              }
              $reportPath = [IO.Path]::GetFullPath(
                ([string]$reportLine -replace '^Отчёт:\\s*', '').Trim()
              )
              if (-not (Test-Path -LiteralPath $reportPath -PathType Leaf)) {
                throw "Rapid import $number report does not exist: $reportPath"
              }
              if (-not ([IO.Path]::GetDirectoryName($reportPath)).Equals(
                $outputDirectory, [StringComparison]::OrdinalIgnoreCase
              )) {
                throw "Rapid import $number wrote outside the installed output directory."
              }
              $createdOutputPaths += $reportPath
            }
            $created = $createdOutputPaths.Count
            "RAPID_OUTPUTS_CREATED=$created" | Add-Content $trace
            if ($created -ne 20) {
              throw "Rapid imports did not create twenty distinct results."
            }
            if (@($createdOutputPaths | Sort-Object -Unique).Count -ne 20) {
              throw "Output filename collision detected."
            }
'''
if text.count(old) != 1:
    raise SystemExit(f'QUR2_OLD_RAPID_VERIFIER_COUNT={text.count(old)}')
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
