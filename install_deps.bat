@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ==============================================================
echo   Step 3: Installing Dependencies
echo ==============================================================
echo.

REM Check if papertalker environment exists
for /f "tokens=*" %%i in ('conda info --base 2^>nul') do set CONDA_BASE=%%i
if not exist "%CONDA_BASE%\envs\papertalker" (
    echo [ERROR] papertalker environment not found
    exit /b 1
)

echo [1/4] Installing notebooklm-py...
call conda run -n papertalker pip install -e "%~dp0deps\notebooklm-py"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install notebooklm-py
    exit /b 1
)
echo   OK

echo.
echo [2/4] Installing paper-search-mcp...
call conda run -n papertalker pip install -e "%~dp0deps\paper-search-mcp"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install paper-search-mcp
    exit /b 1
)
echo   OK

echo.
echo [3/4] Installing common dependencies...
call conda run -n papertalker pip install python-dotenv httpx rich playwright
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install common dependencies
    exit /b 1
)
echo   OK

echo.
echo [4/4] Installing Playwright browser (may take a while)...
call conda run -n papertalker python -m playwright install chromium
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install playwright browser
    exit /b 1
)
echo   OK

echo.
echo ==============================================================
echo   All dependencies installed successfully!
echo ==============================================================
