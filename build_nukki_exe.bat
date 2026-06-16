@echo off
setlocal

cd /d "%~dp0"

echo [1/3] Checking PyInstaller...
python -m pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo PyInstaller not found. Installing...
    python -m pip install pyinstaller
    if errorlevel 1 (
        echo Failed to install PyInstaller.
        exit /b 1
    )
)

echo [2/3] Building Nukki executable...
python -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --name Nukki ^
    nukki_ui.py

if errorlevel 1 (
    echo Build failed.
    exit /b 1
)

echo [3/3] Build complete.
echo Output: %cd%\dist\Nukki\Nukki.exe
endlocal
