[CmdletBinding()]
param(
    [string]$BundleZip,
    [string]$OutputDirectory,
    [string]$OutputName = "Quantum_WB_Offline_Setup.exe"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"

function Get-Sha256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    return (Get-FileHash -LiteralPath $Path -Algorithm SHA256).Hash.ToLowerInvariant()
}

function Test-CommitSha {
    param([AllowNull()][object]$Value)
    if ($null -eq $Value) {
        return $false
    }
    return ([string]$Value).Trim() -match "^[0-9a-fA-F]{40}$"
}

function Resolve-CSharpCompiler {
    $candidates = @(
        (Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"),
        (Join-Path $env:WINDIR "Microsoft.NET\Framework\v4.0.30319\csc.exe")
    )
    foreach ($candidate in $candidates) {
        if (Test-Path -LiteralPath $candidate -PathType Leaf) {
            return $candidate
        }
    }
    throw "Microsoft .NET Framework C# compiler was not found."
}

if ($env:OS -ne "Windows_NT") {
    throw "Quantum EXE installer must be built on Windows."
}

$repositoryRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot "..\..")).Path
if ([string]::IsNullOrWhiteSpace($OutputDirectory)) {
    $OutputDirectory = Join-Path $repositoryRoot "dist\installer-bundles-r2"
}
$OutputDirectory = [IO.Path]::GetFullPath($OutputDirectory)
New-Item -ItemType Directory -Path $OutputDirectory -Force | Out-Null

if ([string]::IsNullOrWhiteSpace($BundleZip)) {
    $BundleZip = Join-Path $OutputDirectory "2_QUANTUM_FULL_OFFLINE_INSTALLER.zip"
}
$BundleZip = [IO.Path]::GetFullPath($BundleZip)
if (-not (Test-Path -LiteralPath $BundleZip -PathType Leaf)) {
    throw "Full offline installer bundle is missing: $BundleZip"
}

$sourceCommit = (& git -C $repositoryRoot rev-parse HEAD).Trim()
if (-not (Test-CommitSha $sourceCommit)) {
    throw "A valid exact source commit is required for EXE build."
}
$targetCommit = $env:TARGET_SHA
if ((Test-CommitSha $targetCommit) -and $targetCommit.Trim().ToLowerInvariant() -ne $sourceCommit.ToLowerInvariant()) {
    throw "EXE source commit does not match TARGET_SHA."
}
$sourceCommit = $sourceCommit.ToLowerInvariant()

$bundleHash = Get-Sha256 -Path $BundleZip
$exePath = Join-Path $OutputDirectory $OutputName
$resultPath = Join-Path $OutputDirectory "exe-installer-result.json"
Remove-Item -LiteralPath $exePath -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $resultPath -Force -ErrorAction SilentlyContinue

$workRoot = Join-Path $env:RUNNER_TEMP ("quantum-exe-builder-{0}" -f [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -Path $workRoot -Force | Out-Null

try {
    $sourcePath = Join-Path $workRoot "QuantumSetup.cs"
    $csharp = @'
using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Security.Cryptography;
using System.Text;
using System.Web.Script.Serialization;

namespace QuantumOfflineSetup
{
    internal static class Program
    {
        private const string ResourceName = "QuantumOfflineBundle.zip";
        private const string ExpectedBundleSha256 = "__BUNDLE_HASH__";
        private const string ExpectedSourceCommit = "__SOURCE_COMMIT__";

        private static int Main(string[] args)
        {
            string temporaryRoot = Path.Combine(
                Path.GetTempPath(),
                "QuantumExeInstall_" + Guid.NewGuid().ToString("N"));
            try
            {
                Directory.CreateDirectory(temporaryRoot);
                string bundlePath = Path.Combine(temporaryRoot, "2_QUANTUM_FULL_OFFLINE_INSTALLER.zip");
                ExtractEmbeddedBundle(bundlePath);
                string actualBundleHash = HashFile(bundlePath);
                if (!String.Equals(actualBundleHash, ExpectedBundleSha256, StringComparison.OrdinalIgnoreCase))
                {
                    throw new InvalidDataException("Embedded Quantum offline bundle SHA-256 mismatch.");
                }

                string expandedRoot = Path.Combine(temporaryRoot, "expanded");
                Directory.CreateDirectory(expandedRoot);
                ZipFile.ExtractToDirectory(bundlePath, expandedRoot);

                string manifestPath = Path.Combine(expandedRoot, "BUNDLE_MANIFEST.json");
                string installerPath = Path.Combine(expandedRoot, "INSTALL_QUANTUM_FULL_OFFLINE.ps1");
                string quantumPackagePath = Path.Combine(expandedRoot, "QuantumLocalProduction_HOME_LOCAL.zip");
                RequireFile(manifestPath);
                RequireFile(installerPath);
                RequireFile(quantumPackagePath);

                JavaScriptSerializer serializer = new JavaScriptSerializer();
                Dictionary<string, object> manifest = serializer.DeserializeObject(
                    File.ReadAllText(manifestPath, Encoding.UTF8)) as Dictionary<string, object>;
                if (manifest == null)
                {
                    throw new InvalidDataException("Embedded installer manifest is invalid.");
                }
                string manifestCommit = ReadManifestString(manifest, "source_commit");
                string expectedQuantumHash = ReadManifestString(manifest, "quantum_package_sha256");
                if (!String.Equals(manifestCommit, ExpectedSourceCommit, StringComparison.OrdinalIgnoreCase))
                {
                    throw new InvalidDataException("Embedded installer source commit mismatch.");
                }
                string actualQuantumHash = HashFile(quantumPackagePath);
                if (!String.Equals(actualQuantumHash, expectedQuantumHash, StringComparison.OrdinalIgnoreCase))
                {
                    throw new InvalidDataException("Embedded Quantum package hash does not match its bundle manifest.");
                }

                if (args.Length == 2 && String.Equals(args[0], "--self-test", StringComparison.Ordinal))
                {
                    WriteSelfTestResult(args[1], actualBundleHash, actualQuantumHash);
                    return 0;
                }
                if (args.Length != 0)
                {
                    throw new ArgumentException("Unsupported Quantum setup arguments.");
                }

                ProcessStartInfo startInfo = new ProcessStartInfo();
                startInfo.FileName = "powershell.exe";
                startInfo.Arguments = "-NoProfile -ExecutionPolicy Bypass -File \"" + installerPath.Replace("\"", "\\\"") + "\"";
                startInfo.UseShellExecute = false;
                using (Process process = Process.Start(startInfo))
                {
                    if (process == null)
                    {
                        throw new InvalidOperationException("Quantum offline installer did not start.");
                    }
                    process.WaitForExit();
                    return process.ExitCode;
                }
            }
            catch (Exception exception)
            {
                Console.Error.WriteLine(
                    "QUANTUM_EXE_ERROR: " + exception.GetType().Name + ": " + exception.Message);
                return 1;
            }
            finally
            {
                try
                {
                    if (Directory.Exists(temporaryRoot))
                    {
                        Directory.Delete(temporaryRoot, true);
                    }
                }
                catch
                {
                }
            }
        }

        private static void ExtractEmbeddedBundle(string destinationPath)
        {
            Assembly assembly = Assembly.GetExecutingAssembly();
            using (Stream resource = assembly.GetManifestResourceStream(ResourceName))
            {
                if (resource == null)
                {
                    throw new InvalidDataException("Embedded Quantum offline bundle is missing.");
                }
                using (FileStream destination = new FileStream(destinationPath, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                {
                    resource.CopyTo(destination);
                }
            }
        }

        private static void RequireFile(string path)
        {
            if (!File.Exists(path))
            {
                throw new FileNotFoundException("Required embedded installer file is missing.", path);
            }
        }

        private static string ReadManifestString(Dictionary<string, object> manifest, string key)
        {
            object value;
            if (!manifest.TryGetValue(key, out value) || value == null)
            {
                throw new InvalidDataException("Embedded installer manifest field is missing: " + key);
            }
            string text = Convert.ToString(value, CultureInfo.InvariantCulture);
            if (String.IsNullOrWhiteSpace(text))
            {
                throw new InvalidDataException("Embedded installer manifest field is empty: " + key);
            }
            return text.Trim();
        }

        private static string HashFile(string path)
        {
            using (SHA256 sha256 = SHA256.Create())
            using (FileStream stream = File.OpenRead(path))
            {
                byte[] digest = sha256.ComputeHash(stream);
                StringBuilder builder = new StringBuilder(digest.Length * 2);
                foreach (byte value in digest)
                {
                    builder.Append(value.ToString("x2", CultureInfo.InvariantCulture));
                }
                return builder.ToString();
            }
        }

        private static void WriteSelfTestResult(
            string resultPath,
            string payloadHash,
            string quantumPackageHash)
        {
            if (String.IsNullOrWhiteSpace(resultPath))
            {
                throw new ArgumentException("Self-test result path is required.");
            }
            string fullResultPath = Path.GetFullPath(resultPath);
            string directory = Path.GetDirectoryName(fullResultPath);
            if (!String.IsNullOrWhiteSpace(directory))
            {
                Directory.CreateDirectory(directory);
            }
            Dictionary<string, object> result = new Dictionary<string, object>();
            result["status"] = "PASS";
            result["source_commit"] = ExpectedSourceCommit;
            result["payload_sha256"] = payloadHash;
            result["release_scope"] = "WB_ONLY";
            result["enabled_marketplaces"] = new string[] { "WILDBERRIES" };
            result["deferred_marketplaces"] = new string[] { "OZON" };
            result["marketplace_write_enabled"] = false;
            result["installer_present"] = true;
            result["quantum_package_sha256"] = quantumPackageHash;
            result["native_self_test"] = true;
            JavaScriptSerializer serializer = new JavaScriptSerializer();
            File.WriteAllText(fullResultPath, serializer.Serialize(result), new UTF8Encoding(false));
        }
    }
}
'@
    $csharp = $csharp.Replace("__BUNDLE_HASH__", $bundleHash)
    $csharp = $csharp.Replace("__SOURCE_COMMIT__", $sourceCommit)
    [IO.File]::WriteAllText($sourcePath, $csharp, [Text.Encoding]::ASCII)

    $compiler = Resolve-CSharpCompiler
    $compilerArguments = @(
        "/nologo",
        "/target:exe",
        "/platform:anycpu",
        "/optimize+",
        "/out:$exePath",
        "/resource:$BundleZip,QuantumOfflineBundle.zip",
        "/reference:System.IO.Compression.dll",
        "/reference:System.IO.Compression.FileSystem.dll",
        "/reference:System.Web.Extensions.dll",
        $sourcePath
    )
    $compilerOutput = @(& $compiler @compilerArguments 2>&1)
    $compilerExitCode = $LASTEXITCODE
    $compilerOutput | ForEach-Object { Write-Host $_ }
    if ($compilerExitCode -ne 0) {
        throw "Quantum EXE compilation failed with exit code $compilerExitCode."
    }
    if (-not (Test-Path -LiteralPath $exePath -PathType Leaf)) {
        throw "Quantum EXE installer was not produced: $exePath"
    }

    $exeItem = Get-Item -LiteralPath $exePath
    if ($exeItem.Length -le 0) {
        throw "Quantum EXE installer is empty."
    }
    $signature = Get-AuthenticodeSignature -LiteralPath $exePath
    if ([string]$signature.Status -eq "HashMismatch") {
        throw "Quantum EXE Authenticode hash verification failed."
    }

    $result = [ordered]@{
        installer = "Quantum_WB_Offline_Setup"
        installer_version = "R2_DOTNET_BOOTSTRAP"
        source_commit = $sourceCommit
        release_scope = "WB_ONLY"
        enabled_marketplaces = @("WILDBERRIES")
        deferred_marketplaces = @("OZON")
        marketplace_write_enabled = $false
        payload_bundle = [ordered]@{
            path = $BundleZip
            sha256 = $bundleHash
            size_bytes = (Get-Item -LiteralPath $BundleZip).Length
        }
        exe = [ordered]@{
            path = $exePath
            sha256 = Get-Sha256 -Path $exePath
            size_bytes = $exeItem.Length
            authenticode_status = [string]$signature.Status
            code_signed = ([string]$signature.Status -eq "Valid")
            self_test_argument = "--self-test"
        }
        builder = "WINDOWS_DOTNET_FRAMEWORK_CSC"
        production_release_authorized = $false
    }
    $result | ConvertTo-Json -Depth 7 | Set-Content -LiteralPath $resultPath -Encoding UTF8
    $result | ConvertTo-Json -Depth 7 | Write-Output
}
finally {
    Remove-Item -LiteralPath $workRoot -Recurse -Force -ErrorAction SilentlyContinue
}
