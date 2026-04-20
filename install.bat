@echo off
setlocal enabledelayedexpansion

echo === Installation Agent RAGUIA ===

set "API_BASE=%~1"
set "TOKEN=%~2"
set "WATCH_PARENT=%~3"

if "%API_BASE%"=="" or "%TOKEN%"=="" (
    echo Usage: %0 ^<API_BASE^> ^<AGENT_TOKEN^> [WATCH_PARENT]
    exit /b 1
)

if "%WATCH_PARENT%"=="" set "WATCH_PARENT=%USERPROFILE%\Documents"

set "SCRIPT_DIR=%~dp0"
set "AGENT_DIR=%SCRIPT_DIR%.raguia_agent"

echo.
echo 1. Installation de 'uv' et Python...
where uv >nul 2>&1
if errorlevel 1 (
    powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    set "PATH=%USERPROFILE%\.cargo\bin;%PATH%"
)
call uv python install 3.11

echo.
echo 2. Creation de la configuration...
if not exist "%AGENT_DIR%" mkdir "%AGENT_DIR%"
(
echo api_base: "%API_BASE%"
echo agent_token: "%TOKEN%"
echo watch_parent: "%WATCH_PARENT%"
echo root_folder_name: "RAGUIA"
) > "%AGENT_DIR%\raguia_agent.yaml"

echo.
echo 3. Installation des dependances...
cd /d "%SCRIPT_DIR%"
call uv venv "%AGENT_DIR%\venv" --python 3.11
call "%AGENT_DIR%\venv\Scripts\activate.bat"
call uv pip install -e ".[tray]"

echo.
echo 4. Test de connexion...
python -c "import httpx, yaml, sys; cfg = yaml.safe_load(open(r'%AGENT_DIR%\raguia_agent.yaml')); r = httpx.get(cfg['api_base'] + '/api/portal/agent/sync-status', headers={'Authorization': f'Bearer {cfg[\"agent_token\"]}'}, timeout=10.0); sys.exit(0 if r.status_code == 200 else 1)"
if errorlevel 1 (
    echo   [ERREUR] Connexion echouee
) else (
    echo   Connexion reussie!
)

echo.
echo 5. Creation des scripts...
(
echo @echo off
echo cd /d "%%~dp0"
echo call venv\Scripts\activate.bat
echo set RAGUIA_AGENT_CONFIG=%%~dps0raguia_agent.yaml
echo python -m raguia_local_agent
) > "%AGENT_DIR%\start.bat"

(
echo @echo off
echo cd /d "%%~dp0"
echo call venv\Scripts\activate.bat
echo set RAGUIA_AGENT_CONFIG=%%~dps0raguia_agent.yaml
echo python -m raguia_local_agent --test
) > "%AGENT_DIR%\test.bat"

(
echo @echo off
echo taskkill /F /IM python.exe 2^>nul
echo echo Agent arrete
) > "%AGENT_DIR%\stop.bat"

if not exist "%WATCH_PARENT%\RAGUIA" mkdir "%WATCH_PARENT%\RAGUIA"
echo.
echo === Installation terminee! ===
echo Dossier cible: %WATCH_PARENT%\RAGUIA
endlocal