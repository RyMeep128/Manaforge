@echo off
setlocal
set "MANAFORGE_PROXY=%~dp0Mtg_Projects\mtg_proxy"
if not exist "%MANAFORGE_PROXY%\venv\Scripts\python.exe" (
    call "%MANAFORGE_PROXY%\Setup Print Proxy Prep.cmd"
    if errorlevel 1 exit /b 1
)
set "MANAFORGE_PYTHON=%MANAFORGE_PROXY%\venv\Scripts\pythonw.exe"
if not exist "%MANAFORGE_PYTHON%" set "MANAFORGE_PYTHON=%MANAFORGE_PROXY%\venv\Scripts\python.exe"
start "" "%MANAFORGE_PYTHON%" "%~dp0run_manaforge.py"
endlocal
