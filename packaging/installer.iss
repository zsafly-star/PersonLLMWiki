; PersonLLMWiki Inno Setup 安装包脚本
;
; 用法（由 build_desktop.py 自动调用）：
;   ISCC.exe installer.iss /DAppVersion=1.0.0
;
; 编译前需先执行 PyInstaller，产出 dist/PersonLLMWiki/

#define MyAppName "PersonLLMWiki"
#define MyAppExeName "PersonLLMWiki.exe"

[Setup]
AppId={{PersonLLMWiki-Desktop}}
AppName={#MyAppName}
AppVersion={#AppVersion}
AppPublisher=PersonLLMWiki
DefaultDirName={pf}\PersonLLMWiki
UsePreviousAppDir=yes
CloseApplications=yes
DefaultGroupName=PersonLLMWiki
DisableProgramGroupPage=yes
OutputDir=..\release\installer
OutputBaseFilename=PersonLLMWiki-Setup-{#AppVersion}
Compression=lzma2/ultra64
SolidCompression=yes
PrivilegesRequired=admin
ArchitecturesAllowed=x64
ArchitecturesInstallIn64BitMode=x64
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName=PersonLLMWiki

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "创建桌面快捷方式"; GroupDescription: "附加图标:"; Flags: checkedonce

[Files]
Source: "..\release\dist\PersonLLMWiki\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\PersonLLMWiki"; Filename: "{app}\{#MyAppExeName}"
Name: "{group}\卸载 PersonLLMWiki"; Filename: "{uninstallexe}"
Name: "{commondesktop}\PersonLLMWiki"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "立即启动 PersonLLMWiki"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
Type: filesandordirs; Name: "{app}"

[InstallDelete]
; 覆盖安装时先清理旧版程序文件，避免新旧混用。
; 历史教训：旧版用 base 环境(Python 3.13)打包，会残留 brotlicffi/各种 .cp313 .pyd 等文件，
; 覆盖安装不清除会导致新版(flask 环境 Python 3.10)运行崩溃（如 brotlicffi 缺 error 属性）。
Type: filesandordirs; Name: "{app}\_internal"
Type: filesandordirs; Name: "{app}\seed"

[Code]
const
  SHCNE_ASSOCCHANGED = $08000000;
  SHCNF_IDLIST = $0000;

procedure SHChangeNotify(wEventId: LongWord; uFlags: Cardinal; dwItem1: LongInt; dwItem2: LongInt);
  external 'SHChangeNotify@shell32.dll stdcall';

procedure CurStepChanged(CurStep: TSetupStep);
begin
  if CurStep = ssPostInstall then
  begin
    // 通知 Shell 刷新图标缓存，确保桌面快捷方式和详细信息页图标正确
    SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, 0, 0);
  end;
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  UserDataPath: string;
begin
  if CurUninstallStep = usPostUninstall then
  begin
    // 清理用户数据目录下的 .env，确保下次安装使用默认路径
    UserDataPath := GetEnv('USERPROFILE') + '\.personllmwiki\.env';
    if FileExists(UserDataPath) then
      DeleteFile(UserDataPath);
  end;
end;
