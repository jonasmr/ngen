@echo off

:: Check if a version argument is provided
if "%~1"=="" (
    echo Usage: %0 [version]
    echo Example: %0 17
    exit /b 1
)

set "VS_VERSION=%~1"
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
set SCRIPT_DIR=%~dp0

:: Check for vswhere.exe
if not exist "%VSWHERE%" (
    echo vswhere.exe not found. Make sure Visual Studio is installed.
    exit /b 1
)


for /f "tokens=*" %%i in ('"%VSWHERE%" -version %VS_VERSION% -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath') do set InstallPath=%%i

if "%InstallPath%"=="" (
    echo Visual Studio version %VS_VERSION% not found.
    exit /b 1
)



python "%SCRIPT_DIR%extract_env2.py" "%InstallPath%\Common7\Tools\VsDevCmd.bat" win32-setup-fast.bat


