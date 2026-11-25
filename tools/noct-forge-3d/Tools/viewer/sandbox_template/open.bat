@echo off
setlocal
set "DIR=%~dp0"
if "%DIR:~-1%"=="\" set "DIR=%DIR:~0,-1%"
set "ROOT=%~dp0..\..\..\.."
if not exist "%ROOT%\Tools\forge.py" (
    echo Could not locate the NoctAssetForge3D repository from this sandbox folder.
    echo Expected Tools\forge.py four levels above this folder.
    echo Run the viewer from the repository instead: py -3.12 -m Tools.forge view --all --open --sandbox NAME
    pause
    exit /b 1
)
cd /d "%ROOT%"

py -3.12 --version >nul 2>&1
if errorlevel 1 (
    echo Python 3.12 was not found.
    echo Install Python 3.12 from https://www.python.org/downloads/ ^(include the "py launcher"^),
    echo then run: py -3.12 -m Tools.forge doctor
    pause
    exit /b 1
)

py -3.12 -m Tools.forge view --all --open --sandbox "%DIR%"
if errorlevel 1 (
    echo.
    echo The viewer exited with an error. See the message above.
    pause
)
endlocal
