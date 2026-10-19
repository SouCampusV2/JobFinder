@echo off
REM Build Job Finder for Windows. Run this ON a Windows machine (not on Mac).
REM   1. Install Python 3.11+ from python.org (tick "Add to PATH").
REM   2. Open Command Prompt, cd into the job-scanner folder.
REM   3. Run:  desktop\build_windows.bat
REM Output: dist\Job Finder\Job Finder.exe   (zip the "Job Finder" folder to share)

setlocal
cd /d "%~dp0.."

echo ==^> Installing dependencies...
python -m pip install -r requirements.txt || goto :err
python -m pip install pywebview pyinstaller || goto :err

echo ==^> Cleaning previous build...
if exist build rmdir /s /q build
if exist "dist\Job Finder" rmdir /s /q "dist\Job Finder"

echo ==^> Running PyInstaller...
pyinstaller desktop\JobFinder-win.spec --noconfirm || goto :err

echo ==^> Building the installer (Inno Setup)...
set "ISCC="
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if defined ISCC (
  "%ISCC%" desktop\installer.iss || goto :err
  echo.
  echo Done. Installer: dist\JobFinder-Setup.exe   ^<-- hand THIS to people
) else (
  echo.
  echo Inno Setup not found. App folder is ready: dist\Job Finder\
  echo To build a one-click installer, install Inno Setup 6 from https://jrsoftware.org/isdl.php
  echo then re-run this script ^(or: ISCC.exe desktop\installer.iss^).
)
goto :eof

:err
echo.
echo BUILD FAILED. See the error above.
exit /b 1
