@echo off
chcp 65001 >nul
cd /d "%~dp0"
title fix_db - write app.db back to the PS4

set PROG="%~dp0fix_db.exe"
if not exist "%~dp0fix_db.exe" (
	echo.
	echo fix_db.exe was not found next to this file.
	echo Unpack the whole archive into one folder and run it from there.
	echo.
	pause
	exit /b 1
)

set IP=%1
if "%IP%"=="" set /p IP=PS4 IP address: 
if "%IP%"=="" (
	echo.
	echo No PS4 IP address was given.
	echo.
	pause
	exit /b 1
)

echo.
echo ================================================================
echo   PS4 %IP%   -   WRITES app.db BACK TO THE CONSOLE
echo   A backup of the original app.db is kept in the tmp\backup folder.
echo ================================================================
echo.
%PROG% %IP% --apply
echo.
echo Log the PS4 user out or reboot the console so PS4 reads app.db again.
echo.
pause
