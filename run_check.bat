@echo off
chcp 65001 >nul
cd /d "%~dp0"
title fix_db - check only, nothing is written to the PS4

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
echo   PS4 %IP%   -   CHECK ONLY, nothing is written to the console
echo   Lists the games that are missing in app.db.
echo ================================================================
echo.
%PROG% %IP%
echo.
echo Found a broken row and want it gone? Add --prune:
echo   fix_db.exe %IP% --prune --apply
echo.
pause