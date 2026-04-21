#!/bin/bash
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Erreur: python3 est introuvable. Installe Python 3 puis relance."
  exit 1
fi

if [ ! -f venv/bin/activate ]; then
  python3 -m venv venv || exit 1
fi

source venv/bin/activate
export RAGUIA_AGENT_CONFIG="$(pwd)/raguia_agent.yaml"

# Garantit que le module agent est installe dans le venv.
if ! python3 -c "import raguia_local_agent" >/dev/null 2>&1; then
  python3 -m pip install -e ".." || exit 1
fi

python3 -m raguia_local_agent --test
