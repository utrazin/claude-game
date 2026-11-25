@echo off
cd /d "%~dp0"

py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo Python 3.12 was not found.
    echo Install Python 3.12 from https://www.python.org/downloads/ ^(include the "py launcher"^),
    echo then run: py -3.12 -m Tools.forge doctor
    pause
    exit /b 1
)

py -3.12 -m Tools.forge view --all --open
if errorlevel 1 (
    echo.
    echo The viewer exited with an error. See the message above.
    pause
)
