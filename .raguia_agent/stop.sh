#!/bin/bash
cd "$(dirname "$0")"

PID_FILE="../../../.raguia/agent.pid"
if [ -f "$PID_FILE" ]; then
    pid=$(cat "$PID_FILE" 2>/dev/null)
    if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
        kill "$pid" 2>/dev/null || true
    fi
    rm -f "$PID_FILE" 2>/dev/null || true
fi

for pid in $(pgrep -f "raguia_local_agent" 2>/dev/null); do
    kill "$pid" 2>/dev/null || true
done

echo "Agent arrêté"
