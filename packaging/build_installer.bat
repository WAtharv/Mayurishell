@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo MayuriShell Installer Compiler (Inno Setup 6)
echo ========================================================

cd /d "%~dp0\.."

set MAYURI_VERSION=%~1
if "%MAYURI_VERSION%"=="" (
    for /f "tokens=*" %%v in ('python -c "import core.version; print(core.version.VERSION)" 2^>nul') do set MAYURI_VERSION=%%v
)
if "%MAYURI_VERSION%"=="" set MAYURI_VERSION=0.1.0

set ISCC_EXE=

:: 1. Check PATH
where ISCC.exe >nul 2>&1
if %errorlevel%==0 (
    set "ISCC_EXE=ISCC.exe"
    goto :compile
)

:: 2. Check 32-bit Program Files
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" (
    set "ISCC_EXE=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
    goto :compile
)

:: 3. Check 64-bit Program Files
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" (
    set "ISCC_EXE=%ProgramFiles%\Inno Setup 6\ISCC.exe"
    goto :compile
)

:: 4. Check Local AppData Programs
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" (
    set "ISCC_EXE=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
    goto :compile
)

:not_found
echo.
echo [INFO] Inno Setup 6 compiler (ISCC.exe) was not detected on this system.
echo [INFO] To compile the Windows setup installer (.exe), download and install Inno Setup 6:
echo [INFO]   https://jrsoftware.org/isdl.php
echo [INFO] Skipping installer compilation. The portable release archive (.zip) remains ready for distribution.
exit /b 0

:compile
echo Found Inno Setup Compiler: "%ISCC_EXE%"
echo Compiling MayuriShell v%MAYURI_VERSION% installer...
"%ISCC_EXE%" /DMyAppVersion=%MAYURI_VERSION% "packaging\installer.iss"
if %errorlevel% neq 0 (
    echo [ERROR] Inno Setup compilation failed with error code %errorlevel%.
    exit /b %errorlevel%
)

echo.
echo [SUCCESS] Windows Installer created: dist\MayuriShell-%MAYURI_VERSION%-setup.exe
exit /b 0
