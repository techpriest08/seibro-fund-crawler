; SeibroFundViewer setup.exe 빌드 스크립트 (Inno Setup 6)
;
; 포함 내용:
;   1. dist\SeibroFundViewer.exe (PyInstaller 빌드 결과물)
;   2. Playwright Chromium headless shell + winldd
;      - GUI는 headless=True 로만 브라우저를 쓰므로 전체 Chromium(415MB) 대신
;        headless shell(269MB)만 번들 (실측: headless shell 단독으로 크롤링 동작 확인)
;      - 크롤러 코드가 PLAYWRIGHT_BROWSERS_PATH=%LOCALAPPDATA%\ms-playwright 를
;        강제하므로 설치 위치도 거기에 맞춤
;
; 빌드 전제 조건 (빌드하는 컴퓨터 기준):
;   - dist\SeibroFundViewer.exe 가 이미 빌드되어 있을 것
;   - %LOCALAPPDATA%\ms-playwright 에 chromium_headless_shell-{#ShellVer},
;     winldd-{#WinlddVer} 가 설치되어 있을 것 (python -m playwright install chromium)
;   - ShellVer/WinlddVer 는 playwright 버전 올릴 때 같이 갱신해야 함
;
; 빌드 방법:
;   ISCC.exe installer\SeibroFundViewer.iss
;   → dist\SeibroFundViewer_Setup.exe 생성

#define MyAppName "SeibroFundViewer"
#define MyAppVersion "1.0.0"
#define MyAppExeName "SeibroFundViewer.exe"
#define BrowsersSrc GetEnv("LOCALAPPDATA") + "\ms-playwright"
#define ShellVer "1228"
#define WinlddVer "1007"

[Setup]
AppId={{8B2F4E71-9C3A-4D5B-A6E8-1F7D2C9B0A43}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=techpriest08
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
; 사용자 폴더에만 설치하므로 관리자 권한 불필요
PrivilegesRequired=lowest
OutputDir=..\dist
OutputBaseFilename=SeibroFundViewer_Setup
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "korean"; MessagesFile: "compiler:Languages\Korean.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\{#MyAppExeName}"; DestDir: "{app}"; Flags: ignoreversion
; Playwright 브라우저 — 다른 playwright 사용처와 공유되는 전역 캐시 위치라
; 프로그램 제거 시에도 지우지 않는다 (uninsneveruninstall)
Source: "{#BrowsersSrc}\chromium_headless_shell-{#ShellVer}\*"; DestDir: "{localappdata}\ms-playwright\chromium_headless_shell-{#ShellVer}"; Flags: ignoreversion recursesubdirs createallsubdirs uninsneveruninstall
Source: "{#BrowsersSrc}\winldd-{#WinlddVer}\*"; DestDir: "{localappdata}\ms-playwright\winldd-{#WinlddVer}"; Flags: ignoreversion recursesubdirs createallsubdirs uninsneveruninstall

[Icons]
Name: "{group}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"
Name: "{userdesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent
