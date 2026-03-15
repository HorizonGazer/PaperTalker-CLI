@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ==============================================================
echo   Step 2: Creating Python Environment
echo ==============================================================
echo.

REM Get conda base directory
for /f "tokens=*" %%i in ('conda info --base 2^>nul') do set CONDA_BASE=%%i

REM Check if environment directory exists
if exist "%CONDA_BASE%\envs\papertalker" (
    REM Verify it's a valid conda environment by checking for python.exe
    if exist "%CONDA_BASE%\envs\papertalker\python.exe" (
        echo   OK - Environment already exists
        exit /b 0
    ) else (
        echo   Warning - Invalid environment directory found, removing...
        rmdir /s /q "%CONDA_BASE%\envs\papertalker"
    )
)

echo   Creating papertalker environment...
call conda create -n papertalker python=3.11 -y
if %errorlevel% neq 0 (
    echo   [ERROR] Failed to create environment
    exit /b 1
)

echo.
echo ==============================================================
echo   Environment created successfully!
echo ==============================================================
