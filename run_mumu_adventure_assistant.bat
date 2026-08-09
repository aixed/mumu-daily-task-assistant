@echo off
setlocal EnableExtensions
cd /d "%~dp0"

set "APP_SCRIPT=mumu_adventure_assistant.py"
set "REQ_FILE=requirements.txt"
set "PYTHON_EXE="
set "CHECK_ONLY=0"
if /I "%~1"=="--check" set "CHECK_ONLY=1"

call :find_python
if not defined PYTHON_EXE (
    echo Python 3.10+ was not found. Installing Python...
    call :install_python
    call :find_python
)

if not defined PYTHON_EXE (
    echo.
    echo Failed to find or install Python. Please install Python 3.10+ manually:
    echo https://www.python.org/downloads/windows/
    pause
    exit /b 1
)

echo Using Python: %PYTHON_EXE%
"%PYTHON_EXE%" -m pip --version >nul 2>nul
if errorlevel 1 (
    echo Installing pip...
    "%PYTHON_EXE%" -m ensurepip --upgrade
)

echo Installing/updating dependencies...
"%PYTHON_EXE%" -m pip install --upgrade pip
if exist "%REQ_FILE%" (
    "%PYTHON_EXE%" -m pip install -r "%REQ_FILE%"
) else (
    "%PYTHON_EXE%" -m pip install Pillow psutil
)
if errorlevel 1 (
    echo.
    echo Dependency installation failed.
    pause
    exit /b 1
)

if "%CHECK_ONLY%"=="1" (
    echo Environment check passed.
    exit /b 0
)

echo Starting assistant...
start "" "%PYTHON_EXE%" "%APP_SCRIPT%"
exit /b 0

:find_python
set "PYTHON_EXE="
for %%C in ("py -3.11" "py -3" "python" "python3") do (
    for /f "delims=" %%P in ('%%~C -c "import sys; print(sys.executable if sys.version_info >= (3, 10) else '')" 2^>nul') do (
        if not "%%P"=="" (
            set "PYTHON_EXE=%%P"
            exit /b 0
        )
    )
)
if exist "%LocalAppData%\Programs\Python\Python311\python.exe" (
    set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python311\python.exe"
    exit /b 0
)
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" (
    set "PYTHON_EXE=%LocalAppData%\Programs\Python\Python312\python.exe"
    exit /b 0
)
if exist "%ProgramFiles%\Python311\python.exe" (
    set "PYTHON_EXE=%ProgramFiles%\Python311\python.exe"
    exit /b 0
)
if exist "%ProgramFiles%\Python312\python.exe" (
    set "PYTHON_EXE=%ProgramFiles%\Python312\python.exe"
    exit /b 0
)
exit /b 1

:install_python
where winget >nul 2>nul
if not errorlevel 1 (
    winget install --id Python.Python.3.11 -e --silent --accept-package-agreements --accept-source-agreements
    exit /b 0
)

set "PYTHON_INSTALLER=%TEMP%\python-3.11.9-amd64.exe"
powershell -NoProfile -ExecutionPolicy Bypass -Command "try { [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%PYTHON_INSTALLER%' } catch { exit 1 }"
if errorlevel 1 exit /b 1
"%PYTHON_INSTALLER%" /quiet InstallAllUsers=0 PrependPath=1 Include_pip=1 Include_launcher=1
exit /b 0
