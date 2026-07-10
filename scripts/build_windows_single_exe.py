from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import textwrap
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON_VERSION = "3.13.14"
PYTHON_EMBED_URL = (
    "https://www.python.org/ftp/python/3.13.14/"
    "python-3.13.14-embed-amd64.zip"
)
PYTHON_EMBED_SHA256 = (
    "90b4e5b9898b72d744650524bff92377"
    "c367f44bd5fbd09e3148656c080ad907"
)
APP_VERSION = "quantum-wb-r1"
OUTPUT_NAME = "Quantum_WB_Release.exe"
RESOURCE_NAME = "QuantumPayload"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_verified(url: str, destination: Path, expected_sha256: str) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.exists() and sha256_file(destination) == expected_sha256:
        return
    temporary = destination.with_suffix(destination.suffix + ".part")
    temporary.unlink(missing_ok=True)
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "quantum-windows-builder/1.0"},
    )
    with urllib.request.urlopen(request, timeout=120) as response, temporary.open("wb") as target:
        shutil.copyfileobj(response, target)
    actual = sha256_file(temporary)
    if actual != expected_sha256:
        temporary.unlink(missing_ok=True)
        raise RuntimeError(
            f"embedded Python hash mismatch: expected {expected_sha256}, got {actual}"
        )
    temporary.replace(destination)


def safe_extract(source: Path, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    root = destination.resolve()
    with zipfile.ZipFile(source) as archive:
        for member in archive.infolist():
            target = (destination / member.filename).resolve()
            if root != target and root not in target.parents:
                raise RuntimeError(f"unsafe archive member: {member.filename}")
        archive.extractall(destination)


def configure_embedded_python(payload: Path) -> None:
    pth_files = sorted(payload.glob("python*._pth"))
    if len(pth_files) != 1:
        raise RuntimeError(f"expected one embedded Python _pth file, found {pth_files}")
    pth_files[0].write_text(
        "python313.zip\n.\napp\napp\\src\nimport site\n",
        encoding="utf-8",
        newline="\n",
    )


def copy_application(payload: Path) -> None:
    source_package = ROOT / "src" / "quantum"
    entrypoint = ROOT / "scripts" / "quantum_windows_exe_entry.py"
    if not source_package.is_dir():
        raise RuntimeError(f"missing source package: {source_package}")
    if not entrypoint.is_file():
        raise RuntimeError(f"missing entrypoint: {entrypoint}")

    app_root = payload / "app"
    app_src = app_root / "src"
    shutil.copytree(
        source_package,
        app_src / "quantum",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo"),
    )
    shutil.copy2(entrypoint, app_root / entrypoint.name)
    (payload / "README_RU.txt").write_text(
        "Quantum WB — локальная версия.\n"
        "Запустите Quantum_WB_Release.exe.\n"
        "Пользовательские данные: %USERPROFILE%\\.quantum-analytics\n"
        "Marketplace writes отключены.\n",
        encoding="utf-8",
        newline="\r\n",
    )
    (payload / "APP_VERSION.txt").write_text(
        APP_VERSION + "\n",
        encoding="ascii",
        newline="\n",
    )


def zip_payload(payload: Path, destination: Path) -> None:
    with zipfile.ZipFile(
        destination,
        "w",
        compression=zipfile.ZIP_DEFLATED,
        compresslevel=9,
    ) as archive:
        for path in sorted(payload.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(payload).as_posix())


def csharp_source() -> str:
    return textwrap.dedent(
        f'''\
        using System;
        using System.Diagnostics;
        using System.IO;
        using System.IO.Compression;
        using System.Reflection;
        using System.Windows.Forms;

        internal static class QuantumLauncher
        {{
            private const string AppVersion = "{APP_VERSION}";
            private const string ResourceName = "{RESOURCE_NAME}";

            [STAThread]
            private static int Main(string[] args)
            {{
                try
                {{
                    string target = Environment.GetEnvironmentVariable("QUANTUM_INSTALL_DIR");
                    if (String.IsNullOrWhiteSpace(target))
                    {{
                        target = Path.Combine(
                            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData),
                            "QuantumWB",
                            AppVersion
                        );
                    }}
                    EnsureInstalled(target);
                    return RunApplication(target);
                }}
                catch (Exception error)
                {{
                    MessageBox.Show(
                        error.ToString(),
                        "Quantum WB — ошибка запуска",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error
                    );
                    return 1;
                }}
            }}

            private static void EnsureInstalled(string target)
            {{
                string marker = Path.Combine(target, ".installed");
                if (File.Exists(marker) && File.ReadAllText(marker).Trim() == AppVersion)
                {{
                    return;
                }}

                string parent = Path.GetDirectoryName(target);
                if (String.IsNullOrEmpty(parent))
                {{
                    throw new InvalidOperationException("Invalid installation directory");
                }}
                Directory.CreateDirectory(parent);
                string temporary = target + ".tmp-" + Guid.NewGuid().ToString("N");
                Directory.CreateDirectory(temporary);
                try
                {{
                    Assembly assembly = Assembly.GetExecutingAssembly();
                    using (Stream resource = assembly.GetManifestResourceStream(ResourceName))
                    {{
                        if (resource == null)
                        {{
                            throw new InvalidOperationException("Embedded application payload is missing");
                        }}
                        ExtractArchive(resource, temporary);
                    }}
                    File.WriteAllText(Path.Combine(temporary, ".installed"), AppVersion);
                    if (Directory.Exists(target))
                    {{
                        Directory.Delete(target, true);
                    }}
                    Directory.Move(temporary, target);
                    temporary = null;
                }}
                finally
                {{
                    if (!String.IsNullOrEmpty(temporary) && Directory.Exists(temporary))
                    {{
                        Directory.Delete(temporary, true);
                    }}
                }}
            }}

            private static void ExtractArchive(Stream source, string target)
            {{
                string root = Path.GetFullPath(target + Path.DirectorySeparatorChar);
                using (ZipArchive archive = new ZipArchive(source, ZipArchiveMode.Read, false))
                {{
                    foreach (ZipArchiveEntry entry in archive.Entries)
                    {{
                        string destination = Path.GetFullPath(Path.Combine(target, entry.FullName));
                        if (!destination.StartsWith(root, StringComparison.OrdinalIgnoreCase))
                        {{
                            throw new InvalidOperationException("Unsafe embedded archive path");
                        }}
                        if (String.IsNullOrEmpty(entry.Name))
                        {{
                            Directory.CreateDirectory(destination);
                            continue;
                        }}
                        string directory = Path.GetDirectoryName(destination);
                        if (!String.IsNullOrEmpty(directory))
                        {{
                            Directory.CreateDirectory(directory);
                        }}
                        using (Stream input = entry.Open())
                        using (FileStream output = new FileStream(
                            destination,
                            FileMode.Create,
                            FileAccess.Write,
                            FileShare.None
                        ))
                        {{
                            input.CopyTo(output);
                        }}
                    }}
                }}
            }}

            private static int RunApplication(string target)
            {{
                bool smoke = String.Equals(
                    Environment.GetEnvironmentVariable("QUANTUM_NO_BROWSER"),
                    "1",
                    StringComparison.Ordinal
                );
                string python = Path.Combine(target, smoke ? "python.exe" : "pythonw.exe");
                string script = Path.Combine(target, "app", "quantum_windows_exe_entry.py");
                if (!File.Exists(python) || !File.Exists(script))
                {{
                    throw new FileNotFoundException("Installed Quantum runtime is incomplete");
                }}
                ProcessStartInfo start = new ProcessStartInfo();
                start.FileName = python;
                start.Arguments = "\"" + script.Replace("\"", "\\\"") + "\"";
                start.WorkingDirectory = target;
                start.UseShellExecute = false;
                Process child = Process.Start(start);
                if (child == null)
                {{
                    throw new InvalidOperationException("Failed to start Quantum runtime");
                }}
                child.WaitForExit();
                return child.ExitCode;
            }}
        }}
        '''
    )


def find_csc() -> Path:
    windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
    candidates = [
        windir / "Microsoft.NET" / "Framework64" / "v4.0.30319" / "csc.exe",
        windir / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise RuntimeError(f"C# compiler not found: {candidates}")


def compile_launcher(source: Path, payload_zip: Path, output: Path) -> None:
    csc = find_csc()
    command = [
        str(csc),
        "/nologo",
        "/target:winexe",
        "/optimize+",
        "/platform:x64",
        f"/out:{output}",
        "/reference:System.dll",
        "/reference:System.Windows.Forms.dll",
        "/reference:System.IO.Compression.dll",
        "/reference:System.IO.Compression.FileSystem.dll",
        f"/resource:{payload_zip},{RESOURCE_NAME}",
        str(source),
    ]
    subprocess.run(command, check=True)
    if not output.is_file() or output.stat().st_size < payload_zip.stat().st_size:
        raise RuntimeError("compiled executable is missing or payload is absent")


def self_check() -> None:
    if len(PYTHON_EMBED_SHA256) != 64:
        raise RuntimeError("invalid embedded Python SHA-256")
    if not PYTHON_EMBED_URL.startswith("https://www.python.org/"):
        raise RuntimeError("embedded Python URL must use python.org HTTPS")
    source = csharp_source()
    for token in (
        RESOURCE_NAME,
        APP_VERSION,
        "QUANTUM_INSTALL_DIR",
        "QUANTUM_NO_BROWSER",
        "Unsafe embedded archive path",
    ):
        if token not in source:
            raise RuntimeError(f"launcher template missing token: {token}")
    if not (ROOT / "scripts" / "quantum_windows_exe_entry.py").is_file():
        raise RuntimeError("Windows entrypoint is missing")
    if not (ROOT / "src" / "quantum").is_dir():
        raise RuntimeError("Quantum source package is missing")


def build() -> Path:
    if os.name != "nt":
        raise RuntimeError("Windows build host required")
    self_check()
    build_root = ROOT / "build" / "windows-single-exe"
    dist = ROOT / "dist"
    shutil.rmtree(build_root, ignore_errors=True)
    build_root.mkdir(parents=True)
    dist.mkdir(parents=True, exist_ok=True)

    embed_zip = build_root / f"python-{PYTHON_VERSION}-embed-amd64.zip"
    download_verified(PYTHON_EMBED_URL, embed_zip, PYTHON_EMBED_SHA256)

    payload = build_root / "payload"
    safe_extract(embed_zip, payload)
    configure_embedded_python(payload)
    copy_application(payload)

    payload_zip = build_root / "quantum-payload.zip"
    zip_payload(payload, payload_zip)
    launcher_source = build_root / "QuantumLauncher.cs"
    launcher_source.write_text(csharp_source(), encoding="utf-8", newline="\n")

    output = dist / OUTPUT_NAME
    output.unlink(missing_ok=True)
    compile_launcher(launcher_source, payload_zip, output)
    print(output)
    print(f"sha256={sha256_file(output)}")
    print(f"size={output.stat().st_size}")
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--self-check", action="store_true")
    args = parser.parse_args()
    if args.self_check:
        self_check()
        print("SELF_CHECK_PASS")
        return
    build()


if __name__ == "__main__":
    main()
