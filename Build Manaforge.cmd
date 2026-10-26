@echo off
setlocal
set "MANAFORGE_ROOT=%~dp0"
set "MANAFORGE_PRODUCTS=%MANAFORGE_ROOT%Mtg_Projects"
set "MANAFORGE_PROXY=%MANAFORGE_PRODUCTS%\mtg_proxy"
set "MANAFORGE_PYTHON=%MANAFORGE_PROXY%\venv\Scripts\python.exe"
rem Collection helpers execute before Analysis applies --paths. Make package
rem roots available to their isolated import subprocesses as well.
set "PYTHONPATH=%MANAFORGE_PRODUCTS%;%MANAFORGE_PRODUCTS%\mtg_core;%MANAFORGE_PROXY%;%PYTHONPATH%"
if not exist "%MANAFORGE_PYTHON%" (
    call "%MANAFORGE_PROXY%\Setup Print Proxy Prep.cmd"
    if errorlevel 1 exit /b 1
)
"%MANAFORGE_PYTHON%" -m pip install pyinstaller
if errorlevel 1 exit /b 1
"%MANAFORGE_PYTHON%" -m PyInstaller --noconfirm --windowed --onedir --name Manaforge ^
    --distpath "%MANAFORGE_PRODUCTS%\dist" --workpath "%MANAFORGE_PRODUCTS%\build\manaforge" ^
    --specpath "%MANAFORGE_PRODUCTS%\build\manaforge" ^
    --paths "%MANAFORGE_PRODUCTS%" --paths "%MANAFORGE_PRODUCTS%\mtg_core" --paths "%MANAFORGE_PROXY%" ^
    --collect-submodules mtg_home --collect-submodules mtg_editor --collect-submodules mtg_ui ^
    --collect-submodules mtg_core --collect-submodules mtg_print --hidden-import mtg_proxy.main ^
    --add-data "%MANAFORGE_PRODUCTS%\mtg_core\mtg_core\data;mtg_core/data" --collect-all ijson ^
    --add-data "%MANAFORGE_PROXY%\vibrance.CUBE;." --add-data "%MANAFORGE_PROXY%\assets;assets" ^
    "%MANAFORGE_ROOT%run_manaforge.py"
if errorlevel 1 exit /b 1
echo Manaforge built at "%MANAFORGE_PRODUCTS%\dist\Manaforge\Manaforge.exe"
endlocal
