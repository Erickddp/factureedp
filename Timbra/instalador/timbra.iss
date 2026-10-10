; Inno Setup: instalador de Timbra para Windows. Lo compila CONSTRUIR_INSTALADOR.bat.
; Sin permisos de administrador: se instala para el usuario. Los datos viven aparte, en %LOCALAPPDATA%\Timbra,
; así que actualizar o desinstalar NO borra facturas, XML ni llaves.
#define Version "2.5.0"

[Setup]
AppId={{6E0D3B5C-4A2F-4C6B-9C1E-EDDP00TIMBRA}
AppName=Timbra
AppVersion={#Version}
AppPublisher=EDDP Servicios
DefaultDirName={localappdata}\Programs\Timbra
DefaultGroupName=Timbra
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=salida
OutputBaseFilename=Timbra-Instalador-{#Version}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
SetupIconFile=timbra.ico
UninstallDisplayIcon={app}\Timbra.exe
CloseApplications=yes
UninstallDisplayName=Timbra · Facturación CFDI 4.0

[Languages]
Name: "es"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "escritorio"; Description: "Acceso directo en el escritorio"; GroupDescription: "Accesos:"
Name: "inicio"; Description: "Abrir Timbra al encender la computadora (recomendado: corre recurrentes, SAT y respaldos)"; GroupDescription: "Arranque:"

[Files]
Source: "..\backend\dist\Timbra\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{group}\Timbra"; Filename: "{app}\Timbra.exe"
Name: "{group}\Carpeta de datos y respaldos"; Filename: "{localappdata}\Timbra"
Name: "{autodesktop}\Timbra"; Filename: "{app}\Timbra.exe"; Tasks: escritorio
Name: "{userstartup}\Timbra"; Filename: "{app}\Timbra.exe"; Parameters: "--sin-navegador"; Tasks: inicio

[Run]
Filename: "{app}\Timbra.exe"; Description: "Abrir Timbra"; Flags: nowait postinstall skipifsilent

[UninstallRun]
Filename: "taskkill"; Parameters: "/IM Timbra.exe /F"; Flags: runhidden; RunOnceId: "CerrarTimbra"
