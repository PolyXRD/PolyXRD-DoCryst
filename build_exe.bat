@echo off
REM Build PolyXRD DoCryst INTERNAL EDITION (onefile exe).
REM Product: dist\PolyXRD-DoCryst-vX.Y.Z.exe (+ fixed-name copy).
REM Version is read from docryst/version.py (single source of truth).
cd /d %~dp0
set PY=D:\Project\XRD\python310\python.exe
if not exist "%PY%" set PY=python

REM Version via temp file: for /f strips inner quotes in child cmd (quoting trap)
"%PY%" -c "from docryst.version import __version__; print(__version__)" > "%TEMP%\docryst_ver.txt" 2>NUL
set /p VER=<"%TEMP%\docryst_ver.txt"

echo Building PolyXRD DoCryst v%VER% (internal edition) ...
"%PY%" -m PyInstaller --noconfirm --clean PolyXRD-DoCryst.spec
if errorlevel 1 goto :fail

if exist "dist\PolyXRD-DoCryst-v%VER%.exe" copy /Y "dist\PolyXRD-DoCryst-v%VER%.exe" "dist\PolyXRD-DoCryst.exe"
echo.
echo Done:
echo   dist\PolyXRD-DoCryst-v%VER%.exe
if exist "dist\PolyXRD-DoCryst.exe" echo   dist\PolyXRD-DoCryst.exe
exit /b 0

:fail
echo.
echo BUILD FAILED
exit /b 1
