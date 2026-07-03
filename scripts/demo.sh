#!/usr/bin/env bash
set -euo pipefail

echo "============================================================"
echo "  Hypothesis Fabric — Demo Script"
echo "  Scenario: increase Au flotation recovery by 5%"
echo "            without raising cyanide use"
echo "============================================================"
echo ""

# ── 1. Check prerequisites ──────────────────────────────────
if [ ! -f .env ]; then
    echo "ERROR: .env file not found. Copy .env_example and fill in API keys."
    exit 1
fi

if ! docker compose ps memgraph 2>/dev/null | grep -q "Up\|running"; then
    echo "Starting Memgraph..."
    docker compose up -d memgraph
    sleep 3
fi

# ── 2. Build KB index ───────────────────────────────────────
echo ""
echo "── Step 1: Build knowledge base index ──"
if [ -d knowledge_base ] && [ "$(ls -A knowledge_base/*.pdf 2>/dev/null)" ]; then
    uv run hfabric index-kb
else
    echo "WARNING: knowledge_base/ is empty or missing."
    echo "         Place metallurgy PDFs in knowledge_base/ and re-run."
    echo "         Proceeding with demo using session-only documents..."
fi

# ── 3. Create session ───────────────────────────────────────
echo ""
echo "── Step 2: Create new session ──"
QUERY="increase Au flotation recovery by 5% without raising cyanide use"
SESSION_OUTPUT=$(uv run hfabric new "$QUERY")
SESSION_ID=$(echo "$SESSION_OUTPUT" | grep "Session created:" | awk '{print $3}')
echo "$SESSION_OUTPUT"
echo "Session ID: $SESSION_ID"

# ── 4. Copy 1-2 KB PDFs to raw_files (demo convenience) ─────
echo ""
echo "── Step 3: Copy reference docs to session ──"
RAW_DIR="sessions/${SESSION_ID}/raw_files"
if [ -d knowledge_base ] && ls knowledge_base/*.pdf 2>/dev/null | head -2 | grep -q .; then
    cp $(ls knowledge_base/*.pdf 2>/dev/null | head -2) "$RAW_DIR/"
    echo "Copied $(ls "$RAW_DIR"/*.pdf 2>/dev/null | wc -l) PDF(s) to $RAW_DIR/"
else
    echo "No KB PDFs to copy. Session will use KB index only."
fi

# ── 5. Run pipeline ─────────────────────────────────────────
echo ""
echo "── Step 4: Run hypothesis generation pipeline ──"
uv run hfabric run "$SESSION_ID" "$QUERY"

# ── 6. Run evals ────────────────────────────────────────────
echo ""
echo "── Step 5: Run evaluation ──"
uv run hfabric eval "$SESSION_ID"

# ── 7. Show export paths ────────────────────────────────────
echo ""
echo "── Export files ──"
EXPORT_DIR="sessions/${SESSION_ID}/export"
if [ -f "$EXPORT_DIR/hypotheses.json" ]; then
    echo "JSON: $EXPORT_DIR/hypotheses.json"
fi
if [ -f "$EXPORT_DIR/report.md" ]; then
    echo "MD:   $EXPORT_DIR/report.md"
    echo ""
    echo "--- First 30 lines of report.md ---"
    head -30 "$EXPORT_DIR/report.md"
fi

echo ""
echo "============================================================"
echo "  Demo complete!"
echo "============================================================"
