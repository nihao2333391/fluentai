@echo off
setlocal
cd /d "%~dp0"

set "FLUENT_AI_DATA_DIR=%~dp0.runtime\dev-data"
if exist "%~dp0.venv\Scripts\python.exe" set "FLUENT_AI_PYTHON=%~dp0.venv\Scripts\python.exe"

if not exist "%FLUENT_AI_DATA_DIR%" mkdir "%FLUENT_AI_DATA_DIR%"

if exist "%ProgramFiles%\nodejs\node.exe" set "PATH=%ProgramFiles%\nodejs;%PATH%"
if exist "%LOCALAPPDATA%\Programs\nodejs\node.exe" set "PATH=%LOCALAPPDATA%\Programs\nodejs;%PATH%"
where node >nul 2>nul
if errorlevel 1 goto missing_node
if not exist "%~dp0node_modules\.bin\electron-vite.cmd" goto missing_dependencies

echo Starting Fluent AI desktop app...
call "%~dp0node_modules\.bin\electron-vite.cmd" dev
set "APP_EXIT_CODE=%ERRORLEVEL%"
if not "%APP_EXIT_CODE%"=="0" pause
exit /b %APP_EXIT_CODE%

:missing_node
echo Node.js was not found. Install Node.js 24 or newer, then run this file again.
pause
exit /b 1

:missing_dependencies
echo Project dependencies are missing. Run pnpm install in this folder, then run this file again.
pause
exit /b 1
