@echo off
chcp 65001 >nul
cd /d "%~dp0"

echo.
echo ==============================================================
echo   Step 1: Detecting and Configuring Conda
echo ==============================================================
echo.

set "USE_CONDA=0"

REM Check if conda is available
where conda >nul 2>&1
if %errorlevel% equ 0 (
    set "USE_CONDA=1"
    echo   OK - Conda detected
    goto :configure_mirrors
)

REM Search common paths
set "SEARCH_PATHS=%USERPROFILE%\miniconda3;%USERPROFILE%\Miniconda3;%LOCALAPPDATA%\miniconda3;C:\ProgramData\miniconda3"
for %%p in (%SEARCH_PATHS%) do (
    if exist "%%p\Scripts\conda.exe" (
        set "USE_CONDA=1"
        echo   OK - Found Conda at %%p
        call "%%p\Scripts\activate.bat" >nul 2>&1
        goto :configure_mirrors
    )
)

REM Install Miniconda
echo   Installing Miniconda...
set "MINICONDA_URL=https://mirrors.tuna.tsinghua.edu.cn/anaconda/miniconda/Miniconda3-latest-Windows-x86_64.exe"
set "MINICONDA_INSTALLER=%TEMP%\Miniconda3-installer.exe"
set "CONDA_ROOT=%USERPROFILE%\miniconda3"

powershell -Command "& {[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri '%MINICONDA_URL%' -OutFile '%MINICONDA_INSTALLER%' -UseBasicParsing}" 2>nul
if errorlevel 1 (
    echo   [ERROR] Download failed
    exit /b 1
)

start /wait "" "%MINICONDA_INSTALLER%" /InstallationType=JustMe /RegisterPython=0 /S /D=%CONDA_ROOT%
if not exist "%CONDA_ROOT%\Scripts\conda.exe" (
    echo   [ERROR] Installation failed
    exit /b 1
)

del "%MINICONDA_INSTALLER%" >nul 2>&1
echo   OK - Miniconda installed
set "USE_CONDA=1"
call "%CONDA_ROOT%\Scripts\activate.bat" >nul 2>&1

:configure_mirrors
echo.
echo   Configuring Conda mirrors...
(
echo channels:
echo   - defaults
echo show_channel_urls: true
echo default_channels:
echo   - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/main
echo   - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/r
echo   - https://mirrors.tuna.tsinghua.edu.cn/anaconda/pkgs/msys2
echo custom_channels:
echo   conda-forge: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
echo   pytorch: https://mirrors.tuna.tsinghua.edu.cn/anaconda/cloud
) > "%USERPROFILE%\.condarc"
echo   OK

echo.
echo   Configuring pip mirrors...
if not exist "%USERPROFILE%\pip" mkdir "%USERPROFILE%\pip"
(
echo [global]
echo index-url = https://pypi.tuna.tsinghua.edu.cn/simple
echo [install]
echo trusted-host = pypi.tuna.tsinghua.edu.cn
) > "%USERPROFILE%\pip\pip.ini"
echo   OK

echo.
echo ==============================================================
echo   Conda configuration complete!
echo ==============================================================
