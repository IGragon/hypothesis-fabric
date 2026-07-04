#!/usr/bin/env bash
set -euo pipefail

echo "============================================================"
echo "  Hypothesis Fabric — UI Demo Launcher"
echo "  Starts API + Streamlit UI with a ready knowledge base."
echo "============================================================"
echo ""

cd "$(dirname "$0")/.."

if [ ! -f .env ]; then
    echo "WARNING: .env not found. Copy .env_example and fill in API keys."
fi

if ! docker compose ps memgraph 2>/dev/null | grep -q "Up\|running"; then
    echo "Starting Memgraph..."
    docker compose up -d memgraph
    sleep 3
fi

if [ -d knowledge_base ] && [ "$(ls -A knowledge_base/*.pdf 2>/dev/null)" ]; then
    echo "Building KB index..."
    uv run hfabric index-kb || echo "WARN: index-kb failed (continuing)"
fi

echo ""
echo "── Starting FastAPI backend on :8000 ──"
uv run hfabric serve --port 8000 &
API_PID=$!
sleep 2

echo "── Starting Streamlit UI on :8501 ──"
uv run hfabric serve-ui --port 8501 &
UI_PID=$!

echo ""
echo "============================================================"
echo "  UI:  http://localhost:8501"
echo "  API: http://localhost:8000/docs"
echo "  Press Ctrl-C to stop both."
echo "============================================================"

trap "kill $API_PID $UI_PID 2>/dev/null || true" EXIT INT TERM
wait
