@echo off
setlocal
cd /d "%~dp0\.."
set "PYTHONPATH=%CD%\src"
if not defined QUANTUM_RUNTIME_DIR set "QUANTUM_RUNTIME_DIR=%USERPROFILE%\.quantum-analytics\local-pilot"
if not exist "%QUANTUM_RUNTIME_DIR%" mkdir "%QUANTUM_RUNTIME_DIR%"
start "" "http://127.0.0.1:8080/local-pilot"
python -m quantum.api.local_pilot_server --host 127.0.0.1 --port 8080
endlocal
