@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "ROOT_VENV=%SCRIPT_DIR%..\..\venv\Scripts\python.exe"
pushd "%SCRIPT_DIR%"
if exist "%ROOT_VENV%" (
  "%ROOT_VENV%" "run_mtg_core_admin.py"
) else if exist "venv\Scripts\python.exe" (
  "venv\Scripts\python.exe" "run_mtg_core_admin.py"
) else (
  python "run_mtg_core_admin.py"
)
popd
endlocal
