@echo off

TITLE ThermoChemX Launcher

COLOR 0B
setlocal EnableExtensions

:: ==========================================
:: APP CONFIGURATION
set "APP_NAME=ThermoChemX"
set "SHORTCUT_NAME=ChemX"
set "ICON_NAME=src\thermochemx\assets\gui\chemx_icon.ico"
set "RUN_FILE=Run_ChemX.bat"
:: ==========================================

set "APP_DIR=%~dp0"

:: ---------------------------------------------------------------
:: FIX 0: ALWAYS RUN FROM THE APP FOLDER
:: "Run as administrator" and some shell contexts start a .bat in
:: C:\Windows\System32. Every relative path below (venv\,
:: requirements.txt, app.py, the icon) would then silently resolve
:: to the wrong place. Change to the script's own folder first.
:: ---------------------------------------------------------------
cd /d "%APP_DIR%"

:: ---------------------------------------------------------------
:: FIX 1 (extended): DESKTOP SHORTCUT, REFRESHED ON EVERY RUN
:: - A single PowerShell call resolves the real Desktop folder
::   (OneDrive-safe, as before) AND (re)writes the shortcut. Same
::   per-run cost as the old Desktop lookup alone, but stale or
::   broken shortcuts created by earlier versions now repair
::   themselves automatically (mirrors the macOS launcher fix).
:: - Paths are passed via environment variables ($env:...), never
::   spliced into the PowerShell string, so user names containing
::   spaces or apostrophes cannot break the quoting.
:: - A missing icon file prints a warning instead of failing
::   silently with a default icon.
:: ---------------------------------------------------------------
powershell -NoProfile -Command ^
  "$desk = [Environment]::GetFolderPath('Desktop');" ^
  "$lnk = Join-Path $desk ($env:SHORTCUT_NAME + '.lnk');" ^
  "$existed = Test-Path $lnk;" ^
  "$w = New-Object -ComObject WScript.Shell;" ^
  "$s = $w.CreateShortcut($lnk);" ^
  "$s.TargetPath = Join-Path $env:APP_DIR $env:RUN_FILE;" ^
  "$s.WorkingDirectory = $env:APP_DIR;" ^
  "$icon = Join-Path $env:APP_DIR $env:ICON_NAME;" ^
  "if (Test-Path $icon) { $s.IconLocation = $icon } else { Write-Host ('[!] Icon file not found: ' + $icon); Write-Host '    The shortcut will use a default icon.' };" ^
  "$s.Save();" ^
  "if ($existed) { Write-Host '[*] Desktop shortcut refreshed.' } else { Write-Host ('[+] Shortcut ' + $env:SHORTCUT_NAME + ' created on Desktop!') }"
echo.

echo ===========================================================
echo       Starting %APP_NAME%...
echo ===========================================================
echo.

:: ---------------------------------------------------------------
:: FAST PATH, NOW WITH A HEALTH CHECK
:: Reuse the existing venv, but VERIFY it still runs. A venv breaks
:: silently when the base Python it was built from is uninstalled
:: or upgraded; "activate" would still appear to succeed and the
:: user would hit a cryptic "No Python at ..." error much later.
:: ---------------------------------------------------------------
IF NOT EXIST "venv\Scripts\python.exe" goto :find_python
"venv\Scripts\python.exe" -c "exit()" >nul 2>nul
if not errorlevel 1 (
    echo [1/3] Virtual environment found.
    goto :deps
)
COLOR 0E
echo [!] The existing virtual environment is broken - the Python it was
echo     built from was probably uninstalled or updated.
echo     Rebuilding it now...
echo.
COLOR 0B
rmdir /s /q venv

:find_python
:: ---------------------------------------------------------------
:: FIX 2: BULLETPROOF PYTHON DETECTION
:: We do NOT use `where python` because it also matches python.bat /
:: python.cmd files in the current working directory, which can hijack
:: the launcher. Instead we just try to invoke a harmless command and
:: trust the ERRORLEVEL.
:: ---------------------------------------------------------------
set "PYTHON_CMD="

:: 1. Windows Python Launcher (py.exe lives in C:\Windows\ - cannot be
::    shadowed by a local script). This is the most reliable option.
py -3 -c "exit()" >nul 2>nul
if not errorlevel 1 set "PYTHON_CMD=py -3"

:: 2. Generic 'python' command on PATH.
if not defined PYTHON_CMD (
    python -c "exit()" >nul 2>nul
    if not errorlevel 1 set "PYTHON_CMD=python"
)

:: 3. Miniconda / Anaconda / Miniforge (common locations without PATH)
if not defined PYTHON_CMD (
    if exist "%USERPROFILE%\miniconda3\python.exe"      set PYTHON_CMD="%USERPROFILE%\miniconda3\python.exe"
)
if not defined PYTHON_CMD (
    if exist "%USERPROFILE%\anaconda3\python.exe"       set PYTHON_CMD="%USERPROFILE%\anaconda3\python.exe"
)
if not defined PYTHON_CMD (
    if exist "%LOCALAPPDATA%\miniforge3\python.exe"     set PYTHON_CMD="%LOCALAPPDATA%\miniforge3\python.exe"
)
if not defined PYTHON_CMD (
    if exist "C:\ProgramData\miniconda3\python.exe"     set PYTHON_CMD="C:\ProgramData\miniconda3\python.exe"
)

:: Not found - bail out with an actionable message
if not defined PYTHON_CMD (
    COLOR 0C
    echo.
    echo [ERROR] Python was not found on your system.
    echo.
    echo Please install Python 3.10 or newer from one of these sources:
    echo   - https://www.python.org/downloads/
    echo   - https://docs.conda.io/en/latest/miniconda.html
    echo.
    echo During installation, tick "Add python.exe to PATH", then run this
    echo launcher again.
    echo.
    echo See also the Troubleshooting section of the README.
    echo.
    pause
    exit /b 1
)

:: Capture the detected version so error messages can show it.
set "PY_VER="
for /f "tokens=2" %%v in ('%PYTHON_CMD% -V 2^>^&1') do set "PY_VER=%%v"

:: Version check (>=3.10)
%PYTHON_CMD% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 (
    COLOR 0C
    echo.
    echo [ERROR] Python 3.10 or newer is required.
    echo         Found: Python %PY_VER% via %PYTHON_CMD%
    echo.
    echo Please install a newer version from https://www.python.org/downloads/
    echo and run this launcher again.
    echo.
    echo See also the Troubleshooting section of the README.
    echo.
    pause
    exit /b 1
)

echo [+] Python found: %PYTHON_CMD% (Python %PY_VER%)
echo.

:: ---------------------------------------------------------------
:: FIX 3: RUNTIME-SAFE FAILURE CHECK ON VENV CREATION
:: The old `if %ERRORLEVEL% neq 0` sat inside a parenthesised block,
:: where cmd expands %ERRORLEVEL% at PARSE time - so the check read
:: a stale value and a failed venv creation was never caught. Using
:: `if errorlevel 1` at top level is evaluated at run time.
:: ---------------------------------------------------------------
echo [1/3] Creating virtual environment... This might take a minute.
%PYTHON_CMD% -m venv venv
if errorlevel 1 goto :venv_fail
if not exist "venv\Scripts\python.exe" goto :venv_fail
goto :deps

:venv_fail
COLOR 0C
echo.
echo [ERROR] Failed to create the virtual environment.
echo.
echo You can try the manual installation route instead - from this folder:
echo     %PYTHON_CMD% -m venv venv
echo     venv\Scripts\activate
echo     python -m pip install -r requirements.txt
echo     python app.py
echo.
echo See also the Troubleshooting section of the README.
echo.
pause
exit /b 1

:deps
:: ---------------------------------------------------------------
:: FIX 4: NO "activate" NEEDED
:: The venv's own python.exe is invoked directly. Activation only
:: edits PATH for this console; calling the interpreter by path is
:: equivalent, and cannot be hijacked by other Pythons on PATH.
:: ---------------------------------------------------------------
echo [2/3] Checking dependencies...
"venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 (
    COLOR 0E
    echo.
    echo [WARNING] Some packages failed to install. Network or proxy issues
    echo           are the usual cause. To see the full error, run:
    echo             venv\Scripts\python.exe -m pip install -r requirements.txt
    echo.
    COLOR 0B
)

echo [3/3] Launching %APP_NAME%...
echo.
echo ===========================================================
echo App is running... (Do not close this window)
echo ===========================================================
echo.

"venv\Scripts\python.exe" app.py
set "APP_EXIT=%ERRORLEVEL%"

echo.
echo ===========================================================
if not "%APP_EXIT%"=="0" (
    COLOR 0C
    echo [ERROR] %APP_NAME% closed with an error - exit code %APP_EXIT%.
    echo         The messages above usually explain the cause. See the
    echo         Troubleshooting section of the README for help.
    echo ===========================================================
)
pause
