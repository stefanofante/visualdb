#ifndef AppVersion
#error Define AppVersion with /DAppVersion
#endif
[Setup]
AppId={{2B365F56-C829-4FE7-A607-A2A81DA18930}
AppName=DBVisual
AppVersion={#AppVersion}
DefaultDirName={localappdata}\Programs\DBVisual
DefaultGroupName=DBVisual
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
OutputDir=..\dist
OutputBaseFilename=DBVisual-Windows-x64-Setup
Compression=lzma2/fast
SolidCompression=yes
UninstallDisplayIcon={app}\DBVisual.exe

[Files]
Source: "..\dist\DBVisual\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\build\MicrosoftEdgeWebView2RuntimeInstallerX64.exe"; Flags: dontcopy

[Icons]
Name: "{group}\DBVisual"; Filename: "{app}\DBVisual.exe"

[Code]
function HasRuntime(Root: Integer): Boolean;
var
  Version: String;
begin
  Result := RegQueryStringValue(Root, 'Software\Microsoft\EdgeUpdate\Clients\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}', 'pv', Version)
            and (Version <> '') and (Version <> '0.0.0.0');
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
var
  Code: Integer;
begin
  Result := '';
  if HasRuntime(HKLM32) or HasRuntime(HKCU) then Exit;
  ExtractTemporaryFile('MicrosoftEdgeWebView2RuntimeInstallerX64.exe');
  if not Exec(ExpandConstant('{tmp}\MicrosoftEdgeWebView2RuntimeInstallerX64.exe'), '/silent /install', '', SW_HIDE, ewWaitUntilTerminated, Code) then
    Result := 'Could not start the Microsoft WebView2 Runtime installer.'
  else if (Code <> 0) and not (HasRuntime(HKLM32) or HasRuntime(HKCU)) then
    Result := Format('Microsoft WebView2 Runtime installation failed (%d).', [Code]);
end;
