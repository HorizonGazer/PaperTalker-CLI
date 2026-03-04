@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ==============================================================
echo   PaperTalker-CLI -- One-Click Setup
echo ==============================================================
echo.

REM Step 1: Setup Conda
call "%~dp0setup_conda.bat"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Conda setup failed
    pause
    exit /b 1
)

REM Step 2: Create Environment
call "%~dp0setup_env.bat"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Environment creation failed
    pause
    exit /b 1
)

REM Step 3: Install Dependencies
call "%~dp0install_deps.bat"
if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Dependency installation failed
    pause
    exit /b 1
)

REM Step 4: Check Authentication
echo.
echo ==============================================================
echo   Step 4: Checking Authentication
echo ==============================================================
echo.
if exist "%USERPROFILE%\.notebooklm\storage_state.json" (
    echo   OK - Auth file exists
) else (
    echo   Warning - Auth file not found
    echo   Please run: notebooklm login
)

REM Done
echo.
echo ==============================================================
echo   Installation Complete!
echo ==============================================================
echo.
echo   Usage:
echo     1. conda activate papertalker
echo     2. notebooklm login  (if not already logged in)
echo     3. python quick_video.py "your topic"
echo.

timeout /t 3 >nul 2>&1
start "PaperTalker-CLI" cmd /k "conda activate papertalker && echo. && echo Environment activated! && echo."
