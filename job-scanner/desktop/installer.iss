; Inno Setup script — builds a proper Windows installer for Job Finder.
;
; Prereq: build the app first (desktop\build_windows.bat) so "dist\Job Finder\"
; exists, then compile this with Inno Setup:
;     "C:\Program Files (x86)\Inno Setup 6\ISCC.exe" desktop\installer.iss
; (or just run desktop\build_windows.bat — it calls ISCC automatically if found)
;
; Output: dist\JobFinder-Setup.exe   ← the finished installer to hand people.
; Paths below are relative to THIS script's folder (desktop\).

#define MyAppName "Job Finder"
#define MyAppVersion "1.0.0"
#define MyAppExeName "Job Finder.exe"
#define MyAppPublisher "Andrii Stakhov"

[Setup]
AppId={{B7E9F2A1-4C3D-4E6F-9A2B-JOBFINDER001}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher={#MyAppPublisher}
; Per-user install → no admin rights needed.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\Job Finder
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=JobFinder-Setup
SetupIconFile=icon.ico
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"

[Files]
; The whole PyInstaller output folder.
Source: "..\dist\Job Finder\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
