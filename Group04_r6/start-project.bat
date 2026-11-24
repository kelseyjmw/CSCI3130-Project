@echo off
setlocal
cd /d "%~dp0"
set "PROJECT_PYTHON=%~dp0backend\venv\Scripts\python.exe"

where npm.cmd >nul 2>&1
if errorlevel 1 (
    echo Node.js and npm are required. Install Node.js, then run this file again.
    goto failed
)

if not exist "%PROJECT_PYTHON%" (
    echo Creating the Python virtual environment...
    where py >nul 2>&1
    if errorlevel 1 (
        python -m venv backend\venv
    ) else (
        py -3 -m venv backend\venv
    )
    if errorlevel 1 goto failed
)

echo Preparing backend dependencies...
"%PROJECT_PYTHON%" -m pip install -r requirements.txt --disable-pip-version-check
if errorlevel 1 goto failed

echo Preparing frontend dependencies...
call npm.cmd --prefix frontend install --no-audit --no-fund --prefer-offline
if errorlevel 1 goto failed

echo Applying database migrations...
"%PROJECT_PYTHON%" backend\manage.py migrate --noinput
if errorlevel 1 goto failed

echo Loading catalog categories and attributes...
"%PROJECT_PYTHON%" backend\manage.py seed_catalog
if errorlevel 1 goto failed

echo Starting the project at http://127.0.0.1:5173
echo Close the three service windows to stop the project.
pushd "%~dp0backend"
start "Group04 - Backend" cmd.exe /k ""%PROJECT_PYTHON%" manage.py runserver 127.0.0.1:8000"
start "Group04 - Listing maintenance" cmd.exe /k ""%PROJECT_PYTHON%" manage.py process_listings --watch"
popd
pushd "%~dp0frontend"
start "Group04 - Frontend" cmd.exe /k "npm.cmd run dev -- --host 127.0.0.1 --port 5173 --strictPort --open"
popd
exit /b 0

:failed
echo.
echo Startup stopped. Check the error above.
echo Python, Node.js and the project's .env configuration must be available.
pause
exit /b 1
