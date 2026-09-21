@echo off
setlocal
set "EDITOR_PYTHON=%~dp0..\mtg_proxy\venv\Scripts\python.exe"
if not exist "%EDITOR_PYTHON%" set "EDITOR_PYTHON=python"
"%EDITOR_PYTHON%" "%~dp0run_editor.py"
if errorlevel 1 pause
endlocal
