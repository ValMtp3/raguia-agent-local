#!/bin/bash
cd "$(dirname "$0")"
source venv/bin/activate
export RAGUIA_AGENT_CONFIG="$(pwd)/raguia_agent.yaml"
python -m raguia_local_agent
