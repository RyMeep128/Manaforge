@echo off
setlocal

title Build Print Proxy Prep EXE
cd /d "%~dp0"
set "PYTHONPATH=%~dp0..;%~dp0..\mtg_core;%PYTHONPATH%"

if not exist "venv\Scripts\python.exe" (
    echo Virtual environment not found.
    echo Running setup first...
    echo.
    call "%~dp0Setup Print Proxy Prep.cmd"
    if errorlevel 1 exit /b 1
)

echo Installing build dependency...
call "venv\Scripts\python.exe" -m pip install pyinstaller
if errorlevel 1 goto :build_failed

echo Cleaning previous build output...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"

echo Building app bundle...
call "venv\Scripts\pyinstaller.exe" --noconfirm "print_proxy_prep.spec"
if errorlevel 1 goto :build_failed

for /f "tokens=3 delims= " %%V in ('findstr /b "APP_VERSION" constants.py') do set "APP_VERSION=%%~V"
if not defined APP_VERSION (
    echo.
    echo Could not read APP_VERSION from constants.py.
    goto :build_failed
)

set "RELEASE_ZIP=dist\PrintProxyPrep-%APP_VERSION%-win.zip"
echo Creating release zip...
if exist "%RELEASE_ZIP%" del /q "%RELEASE_ZIP%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path 'dist\Print Proxy Prep' -DestinationPath '%RELEASE_ZIP%' -Force"
if errorlevel 1 goto :build_failed

echo.
echo Build complete.
echo EXE folder:
echo   dist\Print Proxy Prep
echo.
echo Main executable:
echo   dist\Print Proxy Prep\Print Proxy Prep.exe
echo.
echo Release zip:
echo   %RELEASE_ZIP%
echo.
pause
exit /b 0

:build_failed
echo.
echo Build failed.
echo Please scroll up for the error details.
echo.
pause
exit /b 1
