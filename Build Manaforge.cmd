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
if not exist "%MANAFORGE_PRODUCTS%\build\gameplay\distribution\xmage\component.json" (
    echo Complete gameplay payload required. Run tools/package_play_runtime.py first.
    exit /b 1
)
rem Do not collect unrelated native DLLs from the caller's developer/tool PATH.
rem In particular, Poppler's ICU has a different ABI from Windows' ICU used by Qt.
set "PATH=%MANAFORGE_PROXY%\venv\Scripts;%SystemRoot%\System32;%SystemRoot%;%SystemRoot%\System32\Wbem"
"%MANAFORGE_PYTHON%" -m PyInstaller --clean --noconfirm --windowed --onedir --name Manaforge ^
    --distpath "%MANAFORGE_PRODUCTS%\dist" --workpath "%MANAFORGE_PRODUCTS%\build\manaforge" ^
    --specpath "%MANAFORGE_PRODUCTS%\build\manaforge" ^
    --paths "%MANAFORGE_PRODUCTS%" --paths "%MANAFORGE_PRODUCTS%\mtg_core" --paths "%MANAFORGE_PROXY%" ^
    --collect-submodules mtg_home --collect-submodules mtg_editor --collect-submodules mtg_ui ^
    --collect-submodules mtg_core --collect-submodules mtg_print --hidden-import mtg_proxy.main ^
    --collect-submodules mtg_play ^
    --add-data "%MANAFORGE_PRODUCTS%\build\gameplay\distribution;mtg_play/distribution" ^
    --add-data "%MANAFORGE_PRODUCTS%\mtg_play\engine-lock.json;mtg_play" ^
    --add-data "%MANAFORGE_PRODUCTS%\mtg_play\artifacts.json;mtg_play" ^
    --add-data "%MANAFORGE_ROOT%tools\check_play_unity_game.py;mtg_play/release-tools" ^
    --add-data "%MANAFORGE_PRODUCTS%\mtg_core\mtg_core\data;mtg_core/data" --collect-all ijson ^
    --add-data "%MANAFORGE_PROXY%\vibrance.CUBE;." --add-data "%MANAFORGE_PROXY%\assets;assets" ^
    "%MANAFORGE_ROOT%run_manaforge.py"
if errorlevel 1 exit /b 1
echo Manaforge built at "%MANAFORGE_PRODUCTS%\dist\Manaforge\Manaforge.exe"
rem PyInstaller can hoist the JRE's legacy VC DLLs into the shared DLL directory.
rem Align it with Qt before startup checks, inventories, and release archives.
"%MANAFORGE_PYTHON%" "%MANAFORGE_ROOT%tools\align_windows_runtime.py" "%MANAFORGE_PRODUCTS%\dist\Manaforge"
if errorlevel 1 exit /b 1
endlocal
