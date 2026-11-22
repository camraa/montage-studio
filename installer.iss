; Installateur Windows de Montage Studio (Inno Setup 6) - compilé par BUILD_EXE.bat
#define AppName "Montage Studio"
#define AppVersion "1.0.0"
#define AppExe "MontageStudio.exe"

[Setup]
AppId={{6F1C2B7A-3D4E-4A8B-9C1D-5E2F7A9B0C11}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppName}
DefaultDirName={localappdata}\Programs\{#AppName}
DefaultGroupName={#AppName}
PrivilegesRequired=lowest
OutputDir=dist
OutputBaseFilename=MontageStudio_Setup_{#AppVersion}
SetupIconFile=icone.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/normal
SolidCompression=no
DiskSpanning=yes
DiskSliceSize=max
WizardStyle=modern
LicenseFile=CONDITIONS.txt
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "fr"; MessagesFile: "compiler:Languages\French.isl"

[Tasks]
Name: "desktopicon"; Description: "Créer un raccourci sur le bureau"; GroupDescription: "Raccourcis :"

[Files]
Source: "dist\MontageStudio\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Désinstaller {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Lancer {#AppName}"; Flags: nowait postinstall skipifsilent
