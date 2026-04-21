#!/bin/bash
# Installation simplifiée de l'agent RAGUIA (macOS / Linux ; détection auto de l'OS)

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== Installation Agent RAGUIA ===${NC}"

API_BASE="${1:-}"
TOKEN="${2:-}"
WATCH_PARENT="${3:-}"

if [[ -z "$API_BASE" ]]; then
    read -r -p "URL du portail (ex: https://raguia.mondomaine.com): " API_BASE
fi
if [[ -z "$TOKEN" ]]; then
    read -r -s -p "Jeton JWT agent: " TOKEN
    echo ""
fi
if [[ -z "$API_BASE" || -z "$TOKEN" ]]; then
    echo -e "${RED}API_BASE et AGENT_TOKEN sont obligatoires.${NC}"
    echo "Usage: $0 <API_BASE> <AGENT_TOKEN> [WATCH_PARENT]"
    exit 1
fi

if [[ -z "$WATCH_PARENT" ]]; then
    read -r -p "Dossier parent (defaut: $HOME/Documents): " WATCH_PARENT
    WATCH_PARENT="${WATCH_PARENT:-$HOME/Documents}"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_DIR="$SCRIPT_DIR/.raguia_agent"
PLIST_LABEL="com.raguia.local.agent"
SYSTEMD_USER_UNIT="raguia-agent.service"

install_autostart_macos() {
    local plist="$HOME/Library/LaunchAgents/${PLIST_LABEL}.plist"
    mkdir -p "$HOME/Library/LaunchAgents"
    cat > "$plist" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key>
  <string>${PLIST_LABEL}</string>
  <key>ProgramArguments</key>
  <array>
    <string>/bin/bash</string>
    <string>${AGENT_DIR}/start.sh</string>
  </array>
  <key>WorkingDirectory</key>
  <string>${AGENT_DIR}</string>
  <key>RunAtLoad</key>
  <true/>
</dict>
</plist>
EOF
    chmod 644 "$plist"
    # Décharger l'ancienne instance si elle existe
    launchctl bootout "gui/$(id -u)" "$plist" 2>/dev/null || launchctl unload "$plist" 2>/dev/null || true
    launchctl bootstrap "gui/$(id -u)" "$plist" 2>/dev/null || launchctl load "$plist" 2>/dev/null || true
    echo -e "  ${GREEN}Démarrage automatique : LaunchAgent installé (~/.raguia_agent/start.sh).${NC}"
    echo "    Fichier : $plist"
}

install_autostart_linux() {
    if ! command -v systemctl &>/dev/null; then
        echo -e "  ${YELLOW}systemd absent : démarrage automatique non configuré (lancez .raguia_agent/start.sh manuellement ou via cron).${NC}"
        return 0
    fi
    local userdir="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
    mkdir -p "$userdir"
    local unit="$userdir/${SYSTEMD_USER_UNIT}"
    cat > "$unit" << EOF
[Unit]
Description=Raguia agent local
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=${AGENT_DIR}
ExecStart=/bin/bash ${AGENT_DIR}/start.sh
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
EOF
    systemctl --user daemon-reload
    systemctl --user enable --now "${SYSTEMD_USER_UNIT}" 2>/dev/null || {
        echo -e "  ${YELLOW}Impossible d'activer le service utilisateur systemd.${NC}"
        echo "    Essayez : loginctl enable-linger \$USER  puis relancez, ou démarrez avec :"
        echo "      systemctl --user start ${SYSTEMD_USER_UNIT}"
        return 0
    }
    echo -e "  ${GREEN}Démarrage automatique : service utilisateur systemd activé.${NC}"
    echo "    Unit : $unit"
}

echo -e "\n${GREEN}1. Installation de 'uv' et Python...${NC}"
if ! command -v uv &> /dev/null; then
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.cargo/bin:$PATH"
fi
uv python install 3.11

echo -e "\n${GREEN}2. Création de la configuration...${NC}"
mkdir -p "$AGENT_DIR"
cat > "$AGENT_DIR/raguia_agent.yaml" << EOF
api_base: "$API_BASE"
agent_token: "$TOKEN"
watch_parent: "$WATCH_PARENT"
root_folder_name: "RAGUIA"
EOF

echo -e "\n${GREEN}3. Installation des dépendances...${NC}"
cd "$SCRIPT_DIR"
uv venv "$AGENT_DIR/venv" --python 3.11
source "$AGENT_DIR/venv/bin/activate"
uv pip install -e ".[tray]"

echo -e "\n${GREEN}4. Test de connexion...${NC}"
if python -c "
import httpx, yaml, sys
with open('$AGENT_DIR/raguia_agent.yaml') as f: cfg = yaml.safe_load(f)
r = httpx.get(cfg['api_base'] + '/api/portal/agent/sync-status', headers={'Authorization': f'Bearer {cfg[\"agent_token\"]}'}, timeout=10.0)
if r.status_code != 200:
    sys.exit(1)
data = r.json()
sys.exit(0 if isinstance(data, dict) else 1)
" 2>/dev/null; then
    echo "  Connexion réussie!"
else
    echo -e "${RED}  Échec de connexion au portail.${NC}"
fi

echo -e "\n${GREEN}5. Scripts de contrôle...${NC}"
chmod +x "$AGENT_DIR/start.sh" "$AGENT_DIR/test.sh" "$AGENT_DIR/stop.sh" 2>/dev/null || true

echo -e "\n${GREEN}6. Démarrage automatique (selon l'OS)...${NC}"
case "$(uname -s)" in
    Darwin)   install_autostart_macos ;;
    Linux)    install_autostart_linux ;;
    *)        echo -e "  ${YELLOW}OS non pris en charge pour l'auto-config : exécutez manuellement ${AGENT_DIR}/start.sh${NC}" ;;
esac

mkdir -p "$WATCH_PARENT/RAGUIA"
echo -e "\n${GREEN}=== Installation terminée! ===${NC}"
echo "Dossier cible: $WATCH_PARENT/RAGUIA"
echo "Contrôle : ${AGENT_DIR}/test.sh | start.sh | stop.sh"
