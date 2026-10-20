@echo off
setlocal enabledelayedexpansion

echo ========================================================
echo MayuriShell Windows Repeatable Build
echo ========================================================

cd /d "%~dp0\.."

:: 1. Determine Python interpreter
set "PY_EXE="
if exist ".venv\Scripts\python.exe" (
    set "PY_EXE=.venv\Scripts\python.exe"
) else (
    where python >nul 2>&1
    if %errorlevel%==0 (
        set "PY_EXE=python"
    )
)

if "%PY_EXE%"=="" (
    echo [ERROR] Python 3.11+ interpreter was not found. Please install Python or activate a virtual environment.
    exit /b 1
)

echo Using Python: %PY_EXE%
%PY_EXE% -c "import sys; print(f'Python version: {sys.version.split()[0]}')"
if %errorlevel% neq 0 (
    echo [ERROR] Python failed to execute.
    exit /b 1
)

:: 2. Check Pip
%PY_EXE% -m pip --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] pip module is missing from the Python environment.
    exit /b 1
)

:: 3. Install dependencies
echo.
echo [Step 1/6] Installing dependencies (requirements.txt and requirements-dev.txt)...
%PY_EXE% -m pip install -q -r requirements.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install requirements.txt.
    exit /b 1
)

%PY_EXE% -m pip install -q -r requirements-dev.txt
if %errorlevel% neq 0 (
    echo [ERROR] Failed to install requirements-dev.txt.
    exit /b 1
)

:: 4. Verify PyInstaller is installed
%PY_EXE% -m PyInstaller --version >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller is not available after installation.
    exit /b 1
)

:: 5. Run automated test suite
echo.
echo [Step 2/6] Running automated test suite (pytest)...
%PY_EXE% -m pytest --quiet
if %errorlevel% neq 0 (
    echo [ERROR] Unit tests failed! Aborting build process to prevent defective releases.
    exit /b %errorlevel%
)
echo [PASS] All test suites passed.

:: 6. Query Version
for /f "tokens=*" %%v in ('%PY_EXE% -c "import core.version; print(core.version.VERSION)"') do set MAYURI_VERSION=%%v
if "%MAYURI_VERSION%"=="" set MAYURI_VERSION=0.1.0
echo Packaging version: %MAYURI_VERSION%

:: 7. Clean previous build output (strictly within build/ and dist/MayuriShell)
echo.
echo [Step 3/6] Cleaning previous build folders...
if exist "build" (
    rd /s /q "build"
)
if exist "dist\MayuriShell" (
    rd /s /q "dist\MayuriShell"
)

:: 8. Compile using PyInstaller
echo.
echo [Step 4/6] Compiling standalone executable with PyInstaller...
%PY_EXE% -m PyInstaller "packaging\mayurishell.spec" --noconfirm
if %errorlevel% neq 0 (
    echo [ERROR] PyInstaller compilation failed!
    exit /b %errorlevel%
)

if not exist "dist\MayuriShell\MayuriShell.exe" (
    echo [ERROR] Output binary dist\MayuriShell\MayuriShell.exe was not created!
    exit /b 1
)

:: 9. Run smoke tests on built executable
echo.
echo [Step 5/6] Running smoke tests on compiled executable...
echo Testing: dist\MayuriShell\MayuriShell.exe --version
"dist\MayuriShell\MayuriShell.exe" --version
if %errorlevel% neq 0 (
    echo [ERROR] Smoke test '--version' failed on compiled binary!
    exit /b %errorlevel%
)

echo Testing: dist\MayuriShell\MayuriShell.exe --selftest
"dist\MayuriShell\MayuriShell.exe" --selftest
if %errorlevel% neq 0 (
    echo [ERROR] Smoke test '--selftest' failed on compiled binary!
    exit /b %errorlevel%
)
echo [PASS] Smoke tests completed successfully.

:: 10. Archive into Release Zip and compute SHA256 checksum
echo.
echo [Step 6/6] Creating release archive and computing checksums...
set "ZIP_OUT=dist\MayuriShell-%MAYURI_VERSION%-win64.zip"
set "SHA_OUT=dist\MayuriShell-%MAYURI_VERSION%-win64.zip.sha256"

if exist "%ZIP_OUT%" del /f /q "%ZIP_OUT%"
if exist "%SHA_OUT%" del /f /q "%SHA_OUT%"

powershell -NoProfile -Command "Compress-Archive -Path 'dist\MayuriShell' -DestinationPath '%ZIP_OUT%' -Force"
if %errorlevel% neq 0 (
    echo [ERROR] Failed to create zip archive.
    exit /b %errorlevel%
)

powershell -NoProfile -Command "$h = (Get-FileHash -Algorithm SHA256 '%ZIP_OUT%').Hash.ToLower(); Set-Content -Path '%SHA_OUT%' -Value \"$h *MayuriShell-%MAYURI_VERSION%-win64.zip\""
if %errorlevel% neq 0 (
    echo [ERROR] Failed to generate SHA256 checksum.
    exit /b %errorlevel%
)

echo.
echo ========================================================
echo BUILD SUCCESSFUL
echo ========================================================
echo Standalone folder: dist\MayuriShell\
echo Portable release:  %ZIP_OUT%
echo SHA256 checksum:   %SHA_OUT%
echo.

:: 11. Attempt to build Inno Setup installer if available
call "packaging\build_installer.bat" "%MAYURI_VERSION%"

exit /b 0
