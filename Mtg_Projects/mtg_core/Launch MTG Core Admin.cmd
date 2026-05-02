@echo off
setlocal
set "SCRIPT_DIR=%~dp0"
set "PRODUCT_VENV=%SCRIPT_DIR%..\venv\Scripts\python.exe"
set "PROXY_VENV=%SCRIPT_DIR%..\mtg_proxy\venv\Scripts\python.exe"
set "CORE_VENV=%SCRIPT_DIR%venv\Scripts\python.exe"
set "PYTHON_EXE="

if exist "%PROXY_VENV%" (
  set "PYTHON_EXE=%PROXY_VENV%"
) else if exist "%PRODUCT_VENV%" (
  set "PYTHON_EXE=%PRODUCT_VENV%"
) else if exist "%CORE_VENV%" (
  set "PYTHON_EXE=%CORE_VENV%"
)

pushd "%SCRIPT_DIR%"
set "PYTHONPATH=%SCRIPT_DIR%;%PYTHONPATH%"

if defined PYTHON_EXE (
  "%PYTHON_EXE%" -c "import PyQt6" >nul 2>nul
  if errorlevel 1 (
    echo The configured Python environment cannot import PyQt6:
    echo %PYTHON_EXE%
    echo.
    echo Run ..\mtg_proxy\Setup Print Proxy Prep.cmd first, then try again.
    popd
    endlocal
    exit /b 1
  )
  "%PYTHON_EXE%" "run_mtg_core_admin.py"
) else (
  python -c "import PyQt6" >nul 2>nul
  if errorlevel 1 (
    echo Could not find a Python environment with PyQt6 installed.
    echo.
    echo Run ..\mtg_proxy\Setup Print Proxy Prep.cmd first, then try again.
    popd
    endlocal
    exit /b 1
  )
  python "run_mtg_core_admin.py"
)
popd
endlocal
