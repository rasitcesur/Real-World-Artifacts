@echo off
setlocal
cd /d "%~dp0"
set "OPTIMIZER_BUNDLED_PY=C:\Users\arvasis\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%OPTIMIZER_BUNDLED_PY%" (
    "%OPTIMIZER_BUNDLED_PY%" app.py
) else (
    py -3 app.py
)
if errorlevel 1 pause
