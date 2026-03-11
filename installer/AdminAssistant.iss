#ifndef MyAppName
  #define MyAppName GetStringFileInfo(AddBackslash(SourcePath) + "..\\dist\\AdminAssistant\\AdminAssistant.exe", "ProductName")
  #if MyAppName == ""
    #define MyAppName "Admin Assistant"
  #endif
#endif

#ifndef MyAppVersion
  #error MyAppVersion must be supplied to the installer build.
#endif

#ifndef MyAppPublisher
  #define MyAppPublisher "Dmitrii Fedorov"
#endif

#ifndef MyAppExeName
  #define MyAppExeName "AdminAssistant.exe"
#endif

#ifndef DistDir
  #define DistDir AddBackslash(SourcePath) + "..\\dist\\AdminAssistant"
#endif

[Setup]
AppId={{A4B4D6A0-7E75-4A54-AF4C-9D8C56A0C712}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher=Dmitrii Fedorov
SetupIconFile=..\assets\admin_assistant.ico
AppPublisherURL=https://github.com/fedorovdo
AppSupportURL=https://github.com/fedorovdo
AppUpdatesURL=https://github.com/fedorovdo
DefaultDirName={autopf}\{#MyAppName}
DefaultGroupName=Admin Assistant
DisableProgramGroupPage=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
OutputDir={#SourcePath}
OutputBaseFilename=AdminAssistant_v{#MyAppVersion}_Setup
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\AdminAssistant.exe
VersionInfoCompany=Dmitrii Fedorov
VersionInfoDescription={#MyAppName} Installer
VersionInfoProductName={#MyAppName}
VersionInfoProductVersion={#MyAppVersion}
SetupLogging=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; GroupDescription: "Additional icons:"; Flags: unchecked

[Files]
Source: "{#DistDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "Launch {#MyAppName}"; Flags: nowait postinstall skipifsilent
