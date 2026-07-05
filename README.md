# hypothesis-fabric

Hypothesis Fabric — a metallurgy research hypothesis generation pipeline.

Takes a natural-language research goal (e.g. "increase Au flotation recovery by 5%
without raising cyanide use"), retrieves evidence from a knowledge base of PDFs,
generates ranked hypotheses with citations, scores them, and exports a report.

The pipeline runs as a LangGraph state machine with an LLM confined to declared
slots (rerank, generate, explain). Everything else is deterministic Python.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (package manager)
- Python ≥ 3.13
- Docker (for Memgraph)
- An LLM API key — Yandex AI Studio, RouterAI, ProxyAPI, or DeepSeek
  (default provider is `deepseek`; override via `HFABRIC_PROVIDER` in `.env`
  or `--provider` on the CLI)

Optional (recommended):

- `HF_TOKEN` — HuggingFace access token to avoid rate limits when downloading
  the embeddings model (`intfloat/multilingual-e5-small`, ~120 MB) on first run.
- `MP_API_KEY` — Materials Project key for external grounding.
- `CITRINATION_API_KEY` — Citrination key for material data search.

## Setup

```bash
# 1. Clone the repository
git clone <repo-url> && cd hypothesis-fabric

# 2. Sync dependencies (creates .venv automatically)
uv sync

# 3. Configure environment
cp .env_example .env
# Edit .env and fill in your LLM provider credentials:
#   Provider          Required vars
#   ---------------   -----------------------------------------------
#   deepseek          DEEPSEEK_API_KEY
#   yandex            YC_FOLDER_ID, YC_API_KEY
#   routerai          ROUTERAI_API_KEY
#   proxyapi          PROXY_API_KEY
#
# Select the active provider with HFABRIC_PROVIDER=<deepseek|yandex|routerai|proxyapi>.
# Default is deepseek when unset.
#
# Optional integrations:
#   HF_TOKEN              (HuggingFace — avoids embedding download rate limits)
#   MP_API_KEY            (Materials Project external grounding)
#   CITRINATION_API_KEY   (Citrination material data search)
#   HFABRIC_EXTERNAL_SEARCH  (comma-separated: web,mp,citrination,nims or legacy
#                             presets: web | web+mp | all | none. Default: web)
#   JIRA_BASE_URL, JIRA_API_TOKEN, JIRA_PROJECT_KEY, JIRA_EMAIL  (Jira export)
#   YOUTRACK_BASE_URL, YOUTRACK_TOKEN, YOUTRACK_PROJECT_ID       (YouTrack export)

# 4. Prepare the knowledge base (optional but recommended)
mkdir -p knowledge_base
cp /path/to/metallurgy_pdfs/*.pdf knowledge_base/
uv run hfabric index-kb      # parses PDFs, builds FAISS index, populates Memgraph KG
# Output: knowledge_base/.index/kb/ with faiss.bin and chunks.json

# 5. Start Memgraph
docker compose up -d memgraph
```

## Running the test suite

```bash
# Run all tests (does not require Memgraph or API keys — uses fakes/mocks)
uv run pytest

# Run a specific module's tests
uv run pytest tests/test_orchestrator/
uv run pytest tests/test_integration/
uv run pytest tests/test_cli/

# Run with verbose output
uv run pytest -v

# Run a single test
uv run pytest tests/test_cli/test_golden.py::TestMatchGolden::test_exact_match_passes
```

All 570 tests pass without external services. Tests that would require LLM API
calls or Memgraph use deterministic fakes. Never use bare `pytest` — it may pick
up a system-level pytest that can't find the `hfabric` package.

## Running the application

### One-command demo (recommended for local use)

```bash
bash scripts/demo_ui_v3.sh
```

This is the official launcher. It automates the full stack:

1. **Memgraph** — starts the Docker container if not already running.
2. **KB index** — runs `hfabric index-kb` if `knowledge_base/*.pdf` exists.
3. **FastAPI backend** — `uv run hfabric serve --port 8000` (REST API at
   `http://localhost:8000`, Swagger docs at `http://localhost:8000/docs`).
4. **Streamlit UI v3** — `uv run hfabric serve-ui-v3 --port 8503` (the
   session-based green-themed UI at `http://localhost:8503`).

Both processes run in the background; press **Ctrl-C** to stop both.

| Service      | URL                          | Purpose                          |
|--------------|------------------------------|----------------------------------|
| UI v3        | http://localhost:8503        | Session-based research interface |
| API docs     | http://localhost:8000/docs   | FastAPI Swagger UI               |
| API health   | http://localhost:8000/health | Health check                     |

The UI v3 is the recommended interface. It lets you create sessions, upload
PDF/Excel/Word/image files, set ranking weights, run the pipeline, browse
ranked hypotheses with full justifications and clickable source links, give
feedback, and export reports (JSON / Markdown / DOCX / PDF / CSV).

> **Note:** Place metallurgy PDFs in `knowledge_base/` **before** the first run
> so `index-kb` can build the KB index. You can also upload session-specific
> documents through the UI; they are indexed per-session when you run.

### Manual end-to-end demo (CLI)

If you prefer the command line:

```bash
# 1. Build the KB index (one-time, after placing PDFs in knowledge_base/)
uv run hfabric index-kb

# 2. Create a session (prints a session ID, e.g. a1b2c3d4)
uv run hfabric new "increase Au flotation recovery by 5% without raising cyanide use"

# 3. (Optional) Add session-specific documents
cp /path/to/session_pdfs/*.pdf sessions/a1b2c3d4/raw_files/

# 4. Run the pipeline (8-stage LangGraph: kpi_parse → retrieve → generate →
#    cite_bind → score → constraint_check → explain → export)
uv run hfabric run a1b2c3d4 "increase Au flotation recovery by 5% without raising cyanide use"

# 5. Run evaluations (schema validity, citation existence, constraint pass,
#    Jaccard@10 determinism — target ≥ 0.9 with deterministic LLM)
uv run hfabric eval a1b2c3d4
```

A session directory looks like:

```
sessions/a1b2c3d4/
  raw_files/    ← session-specific PDFs (optional)
  index/        ← session FAISS index (built on run)
  export/       ← output reports (written on run)
  meta.json
```

### Running individual services

```bash
uv run hfabric serve           # FastAPI backend only (port 8000)
uv run hfabric serve-ui-v3     # UI v3 only (port 8503)
uv run hfabric serve-ui        # legacy static UI
uv run hfabric serve-playground # retrieval playground
```

## Project structure

```
src/hfabric/
  cli.py                 # CLI entry point (hfabric command)
  config.py              # MVPConfig dataclass
  contracts.py           # Protocol interfaces for all modules
  schemas.py             # Pydantic models (Hypothesis, KPIParsed, etc.)
  llm.py                 # LLM factory (Yandex / RouterAI / DeepSeek / ProxyAPI)
  embeddings.py          # SentenceTransformersProvider
  etl/                   # PDF parsing, chunking, FAISS index, KG build
  kg/                    # Memgraph KG client + configurable schema
  retriever/             # Query plan, vector search, KG retrieval, rerank, external
  generator/             # Candidate hypothesis synthesizer (LLM)
  scorer/                # Features, weighted ranker, constraint check, calibration
  explain/               # Citation bind, explain slot (LLM, parallel)
  export/                # JSON, Markdown, DOCX, PDF, CSV report writers
  storage/               # SQLite session store
  session/               # SessionManager (directory structure)
  obs/                   # Logging, traces, evals, feedback store
  orchestrator/          # LangGraph state graph + wiring
  api/                   # FastAPI app (sessions, runs, feedback, export, files)
ui_v3/                   # Streamlit UI v3 (session-based, green theme)
hypothesis-fabric-ui/    # Legacy static UI v2
scripts/                 # demo*.sh launchers
knowledge_base/          # Place metallurgy PDFs here
tests/                   # 570 tests across all modules
  golden/                # Hand-authored golden hypotheses
```

## Configuration

All knobs are in `MVPConfig` (`src/hfabric/config.py`). Key fields:

| Field | Default | Description |
|-------|---------|-------------|
| `provider` | `deepseek` | LLM provider (`yandex`/`routerai`/`proxyapi`/`deepseek`/`local`) |
| `model` | provider default | LLM model name |
| `embeddings_model` | `intfloat/multilingual-e5-small` | Sentence transformer model |
| `vector_top_k` | 50 | FAISS results per index |
| `rerank_top_k` | 16 | Chunks after rerank |
| `context_budget_tokens` | 16000 | Max tokens fed to generator |
| `max_explain_hypotheses` | 3 | Top-N hypotheses passed to the explain stage |
| `explain_workers` | 3 | Parallel threads in the explain stage |
| `explain_use_structured_output` | `False` | When `True`, use function-calling structured output for explain (slower, more reliable); when `False`, plain invoke + tag parsing |
| `timeout_explain_per_hypothesis` | 90.0 | Seconds per hypothesis in explain |
| `citation_coverage_min` | 0.5 | FE6 coverage gate |
| `fe2_max_reprompt` | 3 | Generator retry cap |
| `memgraph_uri` | `bolt://localhost:7687` | Memgraph Bolt URI |
| `external_search` | `web+mp` | External grounding: `none`/`web`/`web+mp`/`all` or comma list `web,mp,citrination,nims` |
| `export_format` | `json` | Export format: `json`/`docx`/`pdf`/`csv` |
| `kg_schema_path` | `None` | Optional YAML overriding KG node labels / edge types / domain patterns (R-K4 scalability) |

## Troubleshooting

**Memgraph connection error**: Ensure Docker is running and `docker compose up -d memgraph` succeeded. Check `docker compose ps`.

**LLM API error**: Verify credentials in `.env`. The `HFABRIC_PROVIDER` value must match the keys you provided.

**No hypotheses generated**: Check that `knowledge_base/` contains PDFs and `hfabric index-kb` ran successfully. Session `raw_files/` is optional but recommended for domain-specific evidence.

**`hfabric` command not found**: Use `uv run hfabric` to run the CLI within the project environment, or run `uv sync` to ensure the `.venv` is set up.

**HuggingFace rate-limit warning on first run**: The embeddings model (~120 MB) is downloaded on first use. Set `HF_TOKEN` in `.env` for faster downloads.

**Jaccard@10 below 0.9 with real LLM**: The Jaccard@10 determinism check re-runs the pipeline and compares hypothesis claims. With real LLM calls the output is non-deterministic, so scores below 0.9 are expected. The check is designed for deterministic (mocked) test runs.

**Source links not clickable**: The UI and reports build HTTP file URLs served by the API (`/sessions/{sid}/files/{filename}`). Browsers block `file://` links; ensure the FastAPI backend is running alongside the UI (the demo script starts both).

## Multilingual support

The system handles PDFs in any language. Evidence chunks retain their original
language (e.g. Russian metallurgy texts), while hypotheses are generated in the
language specified by the KPI parser (defaults to English for English queries).
Citation binding uses script detection (Cyrillic vs Latin) to correctly match
cross-language references — when the claim and evidence are in different
scripts, the chunk ID reference is trusted directly.

See `AGENTS.md` for architecture details, design principles, gotchas, and known
issues.