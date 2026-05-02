@echo off
setlocal

title Build Print Proxy Prep EXE

set "PRODUCT_DIR=%~dp0"
set "PROXY_DIR=%PRODUCT_DIR%mtg_proxy"
set "CORE_DIR=%PRODUCT_DIR%mtg_core"
set "BUILD_DIR=%PRODUCT_DIR%build"
set "DIST_DIR=%PRODUCT_DIR%dist"
set "VENV_PYTHON=%PROXY_DIR%\venv\Scripts\python.exe"
set "VENV_PYINSTALLER=%PROXY_DIR%\venv\Scripts\pyinstaller.exe"
set "PYTHONPATH=%PRODUCT_DIR%;%CORE_DIR%;%PYTHONPATH%"

if not exist "%VENV_PYTHON%" (
    echo Virtual environment not found.
    echo Running setup first...
    echo.
    call "%PROXY_DIR%\Setup Print Proxy Prep.cmd"
    if errorlevel 1 exit /b 1
)

echo Installing build dependency...
call "%VENV_PYTHON%" -m pip install pyinstaller
if errorlevel 1 goto :build_failed

echo Cleaning previous build output...
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"

echo Building app bundle...
pushd "%PROXY_DIR%"
call "%VENV_PYINSTALLER%" --noconfirm --distpath "%DIST_DIR%" --workpath "%BUILD_DIR%" "print_proxy_prep.spec"
set "BUILD_RESULT=%ERRORLEVEL%"
popd
if not "%BUILD_RESULT%"=="0" goto :build_failed

for /f "tokens=3 delims= " %%V in ('findstr /b "APP_VERSION" "%PROXY_DIR%\constants.py"') do set "APP_VERSION=%%~V"
if not defined APP_VERSION (
    echo.
    echo Could not read APP_VERSION from mtg_proxy\constants.py.
    goto :build_failed
)

set "RELEASE_ZIP=%DIST_DIR%\PrintProxyPrep-%APP_VERSION%-win.zip"
echo Creating release zip...
if exist "%RELEASE_ZIP%" del /q "%RELEASE_ZIP%"
powershell -NoProfile -ExecutionPolicy Bypass -Command "Compress-Archive -Path '%DIST_DIR%\Print Proxy Prep' -DestinationPath '%RELEASE_ZIP%' -Force"
if errorlevel 1 goto :build_failed

echo.
echo Build complete.
echo EXE folder:
echo   %DIST_DIR%\Print Proxy Prep
echo.
echo Main executable:
echo   %DIST_DIR%\Print Proxy Prep\Print Proxy Prep.exe
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
