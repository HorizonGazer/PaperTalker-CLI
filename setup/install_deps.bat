@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ==============================================================
echo   Step 3: Installing Dependencies
echo ==============================================================
echo.

REM Check if papertalker environment exists and set Python path
for /f "tokens=*" %%i in ('conda info --base 2^>nul') do set CONDA_BASE=%%i
if not exist "%CONDA_BASE%\envs\papertalker" (
    echo [ERROR] papertalker environment not found
    exit /b 1
)

REM Use direct Python path to avoid conda run GBK encoding crash
set "PY=%CONDA_BASE%\envs\papertalker\python.exe"
set "PYTHONIOENCODING=utf-8"

echo [1/6] Installing notebooklm-py...
"%PY%" -m pip install -e "%~dp0..\deps\notebooklm-py"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install notebooklm-py
    exit /b 1
)
echo   OK

echo.
echo [2/6] Installing paper-search-mcp...
"%PY%" -m pip install -e "%~dp0..\deps\paper-search-mcp"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install paper-search-mcp
    exit /b 1
)
echo   OK

echo.
echo [3/6] Installing common dependencies...
"%PY%" -m pip install python-dotenv httpx rich playwright
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install common dependencies
    exit /b 1
)
echo   OK

echo.
echo [4/6] Installing Playwright browser (may take a while)...
"%PY%" -m playwright install chromium
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install playwright browser
    exit /b 1
)
echo   OK

echo.
echo [5/6] Installing downstream dependencies (subtitle + upload)...
"%PY%" -m pip install imageio-ffmpeg faster-whisper jieba "biliup>=1.1.29"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install downstream dependencies
    exit /b 1
)
echo   OK

echo.
echo [6/6] Verifying installation...
"%PY%" -c "import notebooklm, playwright, imageio_ffmpeg, faster_whisper, jieba, biliup; print('All imports OK')"
if %errorlevel% neq 0 (
    echo [WARNING] Some packages may not have installed correctly
) else (
    echo   OK
)

echo.
echo ==============================================================
echo   All dependencies installed successfully!
echo ==============================================================
