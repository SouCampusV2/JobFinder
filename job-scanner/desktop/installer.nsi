; Job Finder — Windows installer, COMPILED ON macOS with makensis.
; Bundles an embeddable CPython 3.11 + Windows wheels + the app source
; (no PyInstaller, so no Windows machine is needed to build). The build script
; desktop/build_windows_installer_macos.sh assembles ./payload next to this file.

Unicode true
!include "MUI2.nsh"

!define APPNAME "Job Finder"
!define COMPANY "Job Finder"
!ifndef APPVERSION
  !define APPVERSION "1.0.0"   ; override with:  makensis -DAPPVERSION=x.y.z
!endif
!define EXENAME "JobFinder-Setup.exe"

Name "${APPNAME}"
OutFile "${EXENAME}"
RequestExecutionLevel user                       ; per-user install → no admin/UAC
InstallDir "$LOCALAPPDATA\Programs\${APPNAME}"
InstallDirRegKey HKCU "Software\${APPNAME}" "InstallDir"
SetCompressor /SOLID lzma

!define MUI_ICON   "payload/app/desktop/icon.ico"
!define MUI_UNICON "payload/app/desktop/icon.ico"
!define MUI_ABORTWARNING

!define MUI_FINISHPAGE_RUN
!define MUI_FINISHPAGE_RUN_TEXT "Launch ${APPNAME} now"
!define MUI_FINISHPAGE_RUN_FUNCTION "LaunchApp"

!insertmacro MUI_PAGE_WELCOME
!insertmacro MUI_PAGE_DIRECTORY
!insertmacro MUI_PAGE_INSTFILES
!insertmacro MUI_PAGE_FINISH
!insertmacro MUI_UNPAGE_CONFIRM
!insertmacro MUI_UNPAGE_INSTFILES
!insertmacro MUI_LANGUAGE "English"

Function LaunchApp
  ; pythonw.exe = no console window.
  Exec '"$INSTDIR\python\pythonw.exe" "$INSTDIR\app\desktop\launcher.py"'
FunctionEnd

; The native window needs Microsoft Edge WebView2. It ships with Windows 11 and
; current Windows 10, but is missing on older/LTSC builds — where the app used
; to start and then silently die. Warn once and offer the official download;
; without it the app still runs, in the browser.
Function CheckWebView2
  ReadRegStr $0 HKLM \
    "SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  StrCmp $0 "" 0 done
  ReadRegStr $0 HKCU \
    "SOFTWARE\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}" "pv"
  StrCmp $0 "" 0 done
    MessageBox MB_YESNO|MB_ICONINFORMATION \
      "Job Finder uses the Microsoft Edge WebView2 runtime for its window.$\r$\n$\r$\n\
It isn't installed on this PC. Job Finder will still work — it will open in your \
browser instead.$\r$\n$\r$\nDownload WebView2 now (recommended)?" IDNO done
    ExecShell "open" "https://developer.microsoft.com/microsoft-edge/webview2/"
  done:
FunctionEnd

Section "Install"
  SetOutPath "$INSTDIR"
  File /r "payload/python"     ; embeddable Python + all wheels (Lib\site-packages)
  File /r "payload/app"        ; application source

  CreateShortcut "$SMPROGRAMS\${APPNAME}.lnk" "$INSTDIR\python\pythonw.exe" \
    '"$INSTDIR\app\desktop\launcher.py"' "$INSTDIR\app\desktop\icon.ico" 0
  CreateShortcut "$DESKTOP\${APPNAME}.lnk" "$INSTDIR\python\pythonw.exe" \
    '"$INSTDIR\app\desktop\launcher.py"' "$INSTDIR\app\desktop\icon.ico" 0

  ; Console launcher: same app via python.exe so a startup error is readable.
  ; This is what to ask a user to run when they report "nothing happens".
  FileOpen  $0 "$INSTDIR\Job Finder (show errors).bat" w
  FileWrite $0 '@echo off$\r$\n'
  FileWrite $0 'echo Starting Job Finder with the console visible...$\r$\n'
  FileWrite $0 '"%~dp0python\python.exe" "%~dp0app\desktop\launcher.py"$\r$\n'
  FileWrite $0 'echo.$\r$\n'
  FileWrite $0 'echo Job Finder exited. Log: %APPDATA%\Job Finder\jobfinder.log$\r$\n'
  FileWrite $0 'pause$\r$\n'
  FileClose $0
  CreateShortcut "$SMPROGRAMS\${APPNAME} (show errors).lnk" \
    "$INSTDIR\Job Finder (show errors).bat" "" "$INSTDIR\app\desktop\icon.ico" 0

  Call CheckWebView2

  WriteRegStr HKCU "Software\${APPNAME}" "InstallDir" "$INSTDIR"
  !define UNINST_KEY "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayName"     "${APPNAME}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayVersion"  "${APPVERSION}"
  WriteRegStr   HKCU "${UNINST_KEY}" "Publisher"       "${COMPANY}"
  WriteRegStr   HKCU "${UNINST_KEY}" "DisplayIcon"     "$INSTDIR\app\desktop\icon.ico"
  WriteRegStr   HKCU "${UNINST_KEY}" "InstallLocation" "$INSTDIR"
  WriteRegStr   HKCU "${UNINST_KEY}" "UninstallString" "$INSTDIR\uninstall.exe"
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoModify" 1
  WriteRegDWORD HKCU "${UNINST_KEY}" "NoRepair" 1
  WriteUninstaller "$INSTDIR\uninstall.exe"
SectionEnd

Section "Uninstall"
  Delete "$SMPROGRAMS\${APPNAME}.lnk"
  Delete "$SMPROGRAMS\${APPNAME} (show errors).lnk"
  Delete "$DESKTOP\${APPNAME}.lnk"
  Delete "$INSTDIR\Job Finder (show errors).bat"
  RMDir /r "$INSTDIR\python"
  RMDir /r "$INSTDIR\app"
  Delete "$INSTDIR\uninstall.exe"
  RMDir "$INSTDIR"
  DeleteRegKey HKCU "Software\Microsoft\Windows\CurrentVersion\Uninstall\${APPNAME}"
  DeleteRegKey HKCU "Software\${APPNAME}"
  ; User data in %APPDATA%\Job Finder (the jobs DB) is intentionally left intact.
SectionEnd
