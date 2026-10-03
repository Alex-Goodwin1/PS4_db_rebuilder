@echo off
chcp 65001 >nul
cd /d "%~dp0"
title build the release archive of fix_db

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0make_dist.ps1"
if errorlevel 1 (
	echo.
	echo make_dist.ps1 failed.
	echo.
	pause
	exit /b 1
)

echo.
pause
