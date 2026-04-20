#!/bin/bash
# Installation simplifiée de l'agent RAGUIA

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${YELLOW}=== Installation Agent RAGUIA ===${NC}"

API_BASE="${1:-}"
TOKEN="${2:-}"
WATCH_PARENT="${3:-}"

if [[ -z "$API_BASE" || -z "$TOKEN" ]]; then
    echo "Usage: $0 <API_BASE> <AGENT_TOKEN> [WATCH_PARENT]"
    exit 1
fi

if [[ -z "$WATCH_PARENT" ]]; then
    WATCH_PARENT="$HOME/Documents"
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
AGENT_DIR="$SCRIPT_DIR/.raguia_agent"

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
sys.exit(0 if r.status_code == 200 else 1)
" 2>/dev/null; then
    echo "  Connexion réussie!"
else
    echo -e "${RED}  Échec de connexion au portail.${NC}"
fi

echo -e "\n${GREEN}5. Création des scripts...${NC}"
cat > "$AGENT_DIR/start.sh" << 'SCRIPT'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
export RAGUIA_AGENT_CONFIG="$(pwd)/raguia_agent.yaml"
python -m raguia_local_agent
SCRIPT
chmod +x "$AGENT_DIR/start.sh"

cat > "$AGENT_DIR/test.sh" << 'SCRIPT'
#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
export RAGUIA_AGENT_CONFIG="$(pwd)/raguia_agent.yaml"
python -m raguia_local_agent --test
SCRIPT
chmod +x "$AGENT_DIR/test.sh"

cat > "$AGENT_DIR/stop.sh" << 'SCRIPT'
#!/bin/bash
pkill -f "raguia_local_agent" 2>/dev/null || true
echo "Agent arrêté"
SCRIPT
chmod +x "$AGENT_DIR/stop.sh"

mkdir -p "$WATCH_PARENT/RAGUIA"
echo -e "\n${GREEN}=== Installation terminée! ===${NC}"
echo "Dossier cible: $WATCH_PARENT/RAGUIA"