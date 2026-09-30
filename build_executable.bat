@echo off
setlocal
cd /d "%~dp0"

where uv >nul 2>&1
if errorlevel 1 (
  echo Run run.bat once so uv and Python are installed, then run this again.
  pause
  exit /b 1
)

uv sync
uv run --with pyinstaller pyinstaller --noconfirm --clean receipt_extractor.spec
if errorlevel 1 (
  echo The executable could not be built.
  pause
  exit /b 1
)

echo.
echo Ready. Double-click dist\ReceiptExtractor\ReceiptExtractor.exe
pause
