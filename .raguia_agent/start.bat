@echo off
cd /d "%~dp0"
call venv\Scripts\activate.bat
set RAGUIA_AGENT_CONFIG=%~dps0raguia_agent.yaml
python -m raguia_local_agent
