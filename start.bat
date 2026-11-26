@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"

echo ==================================================
echo   MaybeAI - Eve Maybe Autonomous AI VTuber Launcher
echo ==================================================

if not exist ".venv\Scripts\python.exe" (
    echo [1/4] Creating virtual environment .venv...
    python -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv. Make sure Python 3.11+ is installed and on PATH.
        pause
        exit /b 1
    )
) else (
    echo [1/4] Virtual environment .venv found.
)

echo [2/4] Installing/updating dependencies from requirements.txt...
".venv\Scripts\python.exe" -m pip install -r requirements.txt
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies from requirements.txt.
    pause
    exit /b 1
)

if not exist ".env" (
    if exist ".env.example" (
        echo [3/4] Creating .env from .env.example...
        copy /y ".env.example" ".env" >nul
    ) else (
        echo [3/4] .env.example not found, skipping .env creation.
    )
) else (
    echo [3/4] .env file found.
)

echo [4/4] Starting MaybeAI (run.py)...
".venv\Scripts\python.exe" run.py %*
endlocal
