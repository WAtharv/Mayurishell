; Inno Setup 6 Script for MayuriShell
; Per-user installer with lowest privileges

#ifndef MyAppVersion
#define MyAppVersion "0.1.0"
#endif

[Setup]
AppId={{B42E7092-230C-4A42-9908-16D72EE131E0}
AppName=MayuriShell
AppVersion={#MyAppVersion}
AppPublisher=MayuriShell
AppPublisherURL=https://github.com/WAtharv/Mayurishell
DefaultDirName={localappdata}\Programs\MayuriShell
DefaultGroupName=MayuriShell
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=MayuriShell-{#MyAppVersion}-setup
Compression=lzma2
SolidCompression=yes
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\MayuriShell.exe
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "..\dist\MayuriShell\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\MayuriShell\MayuriShell"; Filename: "{app}\MayuriShell.exe"; WorkingDir: "{userdocs}"
Name: "{autoprograms}\MayuriShell\MayuriShell (Windows Terminal)"; Filename: "{code:GetWindowsTerminalPath}"; Parameters: """{app}\MayuriShell.exe"""; WorkingDir: "{userdocs}"; Check: IsWindowsTerminalInstalled
Name: "{autodesktop}\MayuriShell"; Filename: "{app}\MayuriShell.exe"; WorkingDir: "{userdocs}"; Tasks: desktopicon

[Run]
Filename: "{app}\MayuriShell.exe"; Description: "{cm:LaunchProgram,MayuriShell}"; Flags: nowait postinstall skipifsilent

[Code]
var
  CachedWTPath: String;
  WTChecked: Boolean;

function FindWindowsTerminal(): String;
var
  LocalAppWT: String;
begin
  if WTChecked then
  begin
    Result := CachedWTPath;
    Exit;
  end;

  WTChecked := True;
  CachedWTPath := '';

  // Check WindowsApps location
  LocalAppWT := ExpandConstant('{localappdata}\Microsoft\WindowsApps\wt.exe');
  if FileExists(LocalAppWT) then
  begin
    CachedWTPath := LocalAppWT;
    Result := CachedWTPath;
    Exit;
  end;

  Result := '';
end;

function IsWindowsTerminalInstalled(): Boolean;
begin
  Result := (FindWindowsTerminal() <> '');
end;

function GetWindowsTerminalPath(Param: String): String;
begin
  Result := FindWindowsTerminal();
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  AppDataDir: String;
  PromptRes: Integer;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // Only prompt if not running in silent uninstall mode
    if not UninstallSilent then
    begin
      AppDataDir := ExpandConstant('{userappdata}\MayuriShell');
      if DirExists(AppDataDir) then
      begin
        PromptRes := MsgBox(
          'Do you want to delete your MayuriShell configuration, history, and logs in %APPDATA%\MayuriShell?' + #13#10 + #13#10 +
          'Select No to keep your personal settings.',
          mbConfirmation,
          MB_YESNO or MB_DEFBUTTON2
        );
        if PromptRes = IDYES then
        begin
          DelTree(AppDataDir, True, True, True);
        end;
      end;
    end;
  end;
end;
