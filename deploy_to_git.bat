@echo off
setlocal

cd /d "%~dp0"

set "COMMIT_MESSAGE=%~1"
if "%COMMIT_MESSAGE%"=="" set "COMMIT_MESSAGE=Update Nukki project"

echo [git] Checking repository...
git rev-parse --is-inside-work-tree >nul 2>&1
if errorlevel 1 (
    echo [git] This folder is not a git repository.
    exit /b 1
)

git remote get-url origin >nul 2>&1
if errorlevel 1 (
    echo [git] origin remote is missing.
    exit /b 1
)

echo [git] Staging changes...
git add -A
if errorlevel 1 (
    echo [git] Failed to stage changes.
    exit /b 1
)

git diff --cached --quiet
if errorlevel 1 (
    echo [git] Creating commit...
    git commit -m "%COMMIT_MESSAGE%"
    if errorlevel 1 (
        echo [git] Commit failed.
        exit /b 1
    )
) else (
    echo [git] No local changes to commit.
)

for /f "delims=" %%B in ('git branch --show-current') do set "BRANCH=%%B"
if "%BRANCH%"=="" set "BRANCH=main"

echo [git] Pushing %BRANCH% to origin...
git push -u origin "%BRANCH%"
if errorlevel 1 (
    echo [git] Push failed.
    exit /b 1
)

echo [git] Deploy complete.
endlocal
