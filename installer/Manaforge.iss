; Side-by-side per-user installs. User data is never part of the payload.
#ifndef AppVersion
  #error AppVersion must be supplied by CI
#endif
[Setup]
AppId={{BF747558-EE57-443D-815F-72F7490108D0}
AppName=Manaforge
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\Manaforge\versions\{#AppVersion}
UsePreviousAppDir=no
DisableDirPage=yes
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
OutputDir=..\installer-output
OutputBaseFilename=Manaforge-Setup
Compression=lzma2
SolidCompression=yes
CloseApplications=no
RestartApplications=no
UninstallFilesDir={localappdata}\Programs\Manaforge\uninstall
WizardStyle=modern

[Tasks]
Name: "desktopicon"; Description: "Create a &desktop shortcut"; Flags: unchecked

[Files]
Source: "..\Mtg_Projects\dist\Manaforge\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\launcher-output\Manaforge.exe"; DestDir: "{localappdata}\Programs\Manaforge"; Flags: ignoreversion

[Icons]
Name: "{userprograms}\Manaforge"; Filename: "{localappdata}\Programs\Manaforge\Manaforge.exe"; WorkingDir: "{localappdata}\Programs\Manaforge"; AppUserModelID: "Manaforge.Desktop"
Name: "{userdesktop}\Manaforge"; Filename: "{localappdata}\Programs\Manaforge\Manaforge.exe"; WorkingDir: "{localappdata}\Programs\Manaforge"; AppUserModelID: "Manaforge.Desktop"; Tasks: desktopicon
Name: "{userdesktop}\Manaforge"; Filename: "{localappdata}\Programs\Manaforge\Manaforge.exe"; WorkingDir: "{localappdata}\Programs\Manaforge"; AppUserModelID: "Manaforge.Desktop"; Check: MigrateDesktopShortcut

[Code]
function OpenProcess(Access: LongWord; Inherit: Boolean; PID: LongWord): THandle;
  external 'OpenProcess@kernel32.dll stdcall';
function WaitForSingleObject(Handle: THandle; Milliseconds: LongWord): LongWord;
  external 'WaitForSingleObject@kernel32.dll stdcall';
function CloseHandle(Handle: THandle): Boolean;
  external 'CloseHandle@kernel32.dll stdcall';

function MigrateDesktopShortcut(): Boolean;
var Shell, Link: Variant; Target, Root, Version: String;
begin
  Result := False;
  if not FileExists(ExpandConstant('{userdesktop}\Manaforge.lnk')) then exit;
  try
    Shell := CreateOleObject('WScript.Shell');
    Link := Shell.CreateShortcut(ExpandConstant('{userdesktop}\Manaforge.lnk'));
    if (Link.Arguments <> '') then exit;
    Target := Link.TargetPath;
    Target := Lowercase(Target);
    Root := Lowercase(ExpandConstant('{localappdata}\Programs\Manaforge\'));
    if Target = Root + 'manaforge.cmd' then begin Result := True; exit; end;
    Root := Root + 'versions\';
    if Pos(Root, Target) <> 1 then exit;
    Version := Copy(Target, Length(Root) + 1, Length(Target));
    Version := ExtractFileDir(Version);
    Result := (Version <> '') and (Pos('\', Version) = 0) and
      (Target = Root + Version + '\manaforge.exe');
  except
    Log('Existing desktop shortcut could not be inspected; left unchanged.');
  end;
end;

function InitializeSetup(): Boolean;
var Id: String; I: Integer;
begin
  Id := ExpandConstant('{param:UPDATEID|}');
  Result := (Id = '') or (Length(Id) = 32);
  for I := 1 to Length(Id) do
    if Pos(Id[I], '0123456789abcdef') = 0 then Result := False;
end;

procedure CurStepChanged(Step: TSetupStep);
var Id, Receipt, Launcher: String; Code, PID: Integer; Handle: THandle;
begin
  if Step <> ssDone then exit;
  Id := ExpandConstant('{param:UPDATEID|}');
  Receipt := '{"version":"{#AppVersion}","update_id":"' + Id + '"}';
  if not SaveStringToFile(ExpandConstant('{app}\manaforge-install.json'), Receipt, False) then
    RaiseException('Cannot write installation completion receipt. Previous installation retained.');
  Launcher := '@echo off' + #13#10 + 'start "" "' + ExpandConstant('{localappdata}\Programs\Manaforge\Manaforge.exe') + '" %*' + #13#10;
  SaveStringToFile(ExpandConstant('{localappdata}\Programs\Manaforge\Manaforge.cmd'), Launcher, False);
  { Updates activate only after the existing application health checks succeed. }
  if Id = '' then begin
    if not Exec(ExpandConstant('{app}\Manaforge.exe'), '--activate-install', ExpandConstant('{app}'), SW_HIDE, ewWaitUntilTerminated, Code) then
      RaiseException('Cannot verify the installation. Previous launcher target retained.');
    if Code <> 0 then
      RaiseException('Installation verification failed. Previous launcher target retained.');
  end;
  if ExpandConstant('{param:NOLAUNCH|0}') = '1' then exit;
  PID := StrToIntDef(ExpandConstant('{param:OLDPID|0}'), 0);
  if PID > 0 then begin
    Handle := OpenProcess($00100000, False, PID);
    if Handle <> 0 then begin
      Code := WaitForSingleObject(Handle, 60000);
      CloseHandle(Handle);
      if Code <> 0 then exit;
    end;
  end;
  if Id = '' then
    Exec(ExpandConstant('{localappdata}\Programs\Manaforge\Manaforge.exe'), '', ExpandConstant('{localappdata}\Programs\Manaforge'), SW_SHOWNORMAL, ewNoWait, Code)
  else
    Exec(ExpandConstant('{app}\Manaforge.exe'), '', ExpandConstant('{app}'), SW_SHOWNORMAL, ewNoWait, Code);
end;
