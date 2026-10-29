@echo off
REM Build PolyXRD DoCryst REGISTERED EDITION (Setup installer):
REM   1. PyInstaller onedir build from PolyXRD-DoCryst-Setup.spec
REM      -> dist\PolyXRD-DoCryst\PolyXRD-DoCryst.exe (+ support files)
REM   2. Inno Setup installer from installer\PolyXRD-DoCryst.iss
REM      -> dist\PolyXRD-DoCryst-vX.Y.Z-Setup.exe
REM Version is read from docryst/version.py (single source of truth).
REM NOTE: keep comments ASCII-only to stay safe under any cmd codepage.
cd /d %~dp0
set PY=D:\Project\XRD\python310\python.exe
if not exist "%PY%" set PY=python
set ISCC=C:\Program Files (x86)\Inno Setup 6\ISCC.exe
if not exist "%ISCC%" set ISCC=ISCC.exe

REM Version via temp file: for /f strips inner quotes in child cmd (quoting trap)
"%PY%" -c "from docryst.version import __version__; print(__version__)" > "%TEMP%\docryst_ver.txt" 2>NUL
set /p VER=<"%TEMP%\docryst_ver.txt"

echo [1/2] Building onedir (registered edition) v%VER% ...
"%PY%" -m PyInstaller --noconfirm --clean PolyXRD-DoCryst-Setup.spec
if errorlevel 1 goto :fail
if not exist "dist\PolyXRD-DoCryst\PolyXRD-DoCryst.exe" goto :fail

echo [2/2] Building installer with Inno Setup ...
"%ISCC%" /DAPP_VER=v%VER% installer\PolyXRD-DoCryst.iss
if errorlevel 1 goto :fail

echo.
echo Done:
echo   dist\PolyXRD-DoCryst\PolyXRD-DoCryst.exe          (onedir, registered edition)
echo   dist\PolyXRD-DoCryst-v%VER%-Setup.exe
exit /b 0

:fail
echo.
echo BUILD FAILED
exit /b 1
