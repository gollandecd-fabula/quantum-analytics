@echo off
setlocal
cd /d "%~dp0\.."
set "PYTHONPATH=%CD%\src"
if not defined QUANTUM_RUNTIME_DIR set "QUANTUM_RUNTIME_DIR=%USERPROFILE%\.quantum-analytics\local-pilot"
if not exist "%QUANTUM_RUNTIME_DIR%" mkdir "%QUANTUM_RUNTIME_DIR%"
if not exist "%QUANTUM_RUNTIME_DIR%\config" mkdir "%QUANTUM_RUNTIME_DIR%\config"
if not exist "%QUANTUM_RUNTIME_DIR%\data" mkdir "%QUANTUM_RUNTIME_DIR%\data"
if not exist "%QUANTUM_RUNTIME_DIR%\uploads" mkdir "%QUANTUM_RUNTIME_DIR%\uploads"
if not exist "%QUANTUM_RUNTIME_DIR%\receipts" mkdir "%QUANTUM_RUNTIME_DIR%\receipts"
if not exist "%QUANTUM_RUNTIME_DIR%\evidence" mkdir "%QUANTUM_RUNTIME_DIR%\evidence"
if not exist "%QUANTUM_RUNTIME_DIR%\output" mkdir "%QUANTUM_RUNTIME_DIR%\output"
if not exist "%QUANTUM_RUNTIME_DIR%\logs" mkdir "%QUANTUM_RUNTIME_DIR%\logs"
start "" "http://127.0.0.1:8080/local-pilot"
where py >nul 2>nul
if %ERRORLEVEL% EQU 0 (
  py -3 -m quantum.api.local_pilot_server --host 127.0.0.1 --port 8080
) else (
  python -m quantum.api.local_pilot_server --host 127.0.0.1 --port 8080
)
endlocal
