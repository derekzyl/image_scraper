@echo off
setlocal
cd /d "%~dp0"

set "UV_DIR=%USERPROFILE%\.local\bin"
set "PATH=%UV_DIR%;%USERPROFILE%\.cargo\bin;%PATH%"

where uv >nul 2>&1
if errorlevel 1 (
  echo uv is not installed. Downloading it now.
  echo uv will also download Python, so a separate Python install is not required.
  set "UV_INSTALL_DIR=%UV_DIR%"
  powershell -NoProfile -ExecutionPolicy Bypass -Command "irm https://astral.sh/uv/install.ps1 | iex"
  set "PATH=%UV_DIR%;%USERPROFILE%\.cargo\bin;%PATH%"
)

where uv >nul 2>&1
if errorlevel 1 (
  echo Could not install uv. Check the internet connection, then run run.bat again.
  pause
  exit /b 1
)

set "PY_VERSION=3.13"
if exist ".python-version" set /p PY_VERSION=<.python-version

echo Checking Python %PY_VERSION% and the app libraries...
uv python install %PY_VERSION%
if errorlevel 1 (
  echo Could not install Python.
  pause
  exit /b 1
)

uv sync
if errorlevel 1 (
  echo Could not install the app libraries.
  pause
  exit /b 1
)

uv run python main.py
if errorlevel 1 (
  echo.
  echo The app closed with an error.
  pause
)
