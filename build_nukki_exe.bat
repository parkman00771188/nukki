@echo off
setlocal

cd /d "%~dp0"

echo [1/4] Checking PyInstaller...
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller.
        exit /b 1
    )
)

echo [2/4] Building Nukki executable...
python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --name Nukki ^
    --add-data "resources;resources" ^
    nukki_ui.py

if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo [3/4] Build complete.
echo Output: %cd%\dist\Nukki\Nukki.exe

echo [4/4] Deploying changes to GitHub...
call "%~dp0deploy_to_git.bat" "Update Nukki project"
if errorlevel 1 (
    echo Git deploy failed.
    exit /b 1
)

endlocal
