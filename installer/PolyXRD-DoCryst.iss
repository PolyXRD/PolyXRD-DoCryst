; Inno Setup 6 script - PolyXRD DoCryst REGISTERED edition installer.
; APP_VER is passed by build_setup.bat as /DAPP_VER=vX.Y.Z (from docryst/version.py).
; Payload: PyInstaller onedir output in ..\dist\PolyXRD-DoCryst\ (build first!).
; Keep comments ASCII-only to stay safe under any compiler codepage.

#define MyAppName "PolyXRD DoCryst"
#ifndef APP_VER
#define APP_VER "v0.0.0"
#endif

[Setup]
AppId=PolyXRD-DoCryst
AppName={#MyAppName}
AppVersion={#APP_VER}
AppPublisher=PolyXRD Team
AppPublisherURL=https://github.com/PolyXRD
AppUpdatesURL=https://github.com/PolyXRD
; Registration state lives in %APPDATA%\PolyXRD\Registration\ and is NOT
; touched by uninstall - re-installing keeps the registration.
DefaultDirName={autopf}\PolyXRD-DoCryst
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
LicenseFile=..\LICENSE-CN
SetupIconFile=..\resources\app-icon.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=admin
OutputDir=..\dist
OutputBaseFilename=PolyXRD-DoCryst-{#APP_VER}-Setup
Uninstallable=yes
CloseApplications=no

[Languages]
Name: "zh"; MessagesFile: "Languages\ChineseSimplified.isl"
Name: "en"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; \
    GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\PolyXRD-DoCryst\*"; DestDir: "{app}"; \
    Flags: recursesubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}"; Filename: "{app}\PolyXRD-DoCryst.exe"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\PolyXRD-DoCryst.exe"; \
    Tasks: desktopicon

[Run]
Filename: "{app}\PolyXRD-DoCryst.exe"; \
    Description: "{cm:LaunchProgram,{#MyAppName}}"; \
    Flags: nowait postinstall skipifsilent
