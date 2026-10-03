@echo off
chcp 65001 >nul
cd /d "%~dp0"
title build fix_db.exe with PyInstaller

where python >nul 2>&1
if errorlevel 1 (
	echo.
	echo Python was not found in PATH. Install Python 3.8 or newer first.
	echo.
	pause
	exit /b 1
)

python -m PyInstaller --version >nul 2>&1
if errorlevel 1 (
	echo.
	echo PyInstaller is missing. Install it with:
	echo   python -m pip install pyinstaller
	echo.
	pause
	exit /b 1
)

echo.
echo ================================================================
echo   building fix_db.exe
echo ================================================================
python -m PyInstaller --onefile --console --clean --noconfirm --name fix_db --distpath . --workpath "%~dp0build" --specpath "%~dp0build" fix_db.py
if errorlevel 1 (
	echo.
	echo build of fix_db failed.
	echo.
	pause
	exit /b 1
)

echo.
echo ================================================================
echo   done: fix_db.exe rebuilt next to this script
echo   the helper copy in the PS4_hide_icons repository must be
echo   replaced with this new fix_db.exe
echo ================================================================
echo.
pause
