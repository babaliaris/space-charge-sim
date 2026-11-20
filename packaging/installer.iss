; Windows installer (Inno Setup 6) of the PyInstaller folder dist\SpaceChargeSimulator.
; Build:  iscc /DMyAppVersion=1.0.0 packaging\installer.iss   ->  dist\SpaceChargeSimulator-<version>-windows-setup.exe
; Installs per user without administrator rights (the user may choose "all users" in the first dialog).

#ifndef MyAppVersion
  #define MyAppVersion "dev"
#endif
#define MyAppName "Space-Charge Simulator"
#define MyAppExe "SpaceChargeSimulator.exe"

[Setup]
AppId={{30E73E6F-9946-46C9-855D-7959A811CDF2}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=Nikolaos Bampaliaris
AppPublisherURL=https://github.com/babaliaris/space-charge-sim
AppSupportURL=https://github.com/babaliaris/space-charge-sim/issues
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
LicenseFile=..\LICENSE
OutputDir=..\dist
OutputBaseFilename=SpaceChargeSimulator-{#MyAppVersion}-windows-setup
SetupIconFile=icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\SpaceChargeSimulator\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
