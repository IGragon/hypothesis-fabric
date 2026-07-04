# hypothesis-fabric

Hypothesis Fabric — a metallurgy research hypothesis generation pipeline.

Takes a natural-language research goal (e.g. "increase Au flotation recovery by 5%
without raising cyanide use"), retrieves evidence from a knowledge base of PDFs,
generates ranked hypotheses with citations, scores them, and exports a report.

## Prerequisites

- [uv](https://docs.astral.sh/uv/) (package manager)
- Python ≥ 3.13
- Docker (for Memgraph)
- A Yandex AI Studio, RouterAI, ProxyAPI, or DeepSeek API key
  (the default provider is `deepseek`; set `provider` in `MVPConfig` or `--provider` on the CLI)
- (Optional) `HF_TOKEN` — HuggingFace access token to avoid rate limits
  when downloading the embeddings model on first run

## Setup

```bash
# 1. Sync dependencies (creates .venv automatically)
uv sync

# 2. Configure environment
cp .env_example .env
# Edit .env and fill in:
#   YC_FOLDER_ID, YC_API_KEY  (for Yandex provider)
#   or ROUTERAI_API_KEY        (for RouterAI provider)
#   or PROXY_API_KEY / DEEPSEEK_API_KEY
# Optional integrations:
#   JIRA_BASE_URL, JIRA_API_TOKEN, JIRA_PROJECT_KEY, JIRA_EMAIL  (Jira export)
#   YOUTRACK_BASE_URL, YOUTRACK_TOKEN, YOUTRACK_PROJECT_ID      (YouTrack export)
#   MP_API_KEY          (Materials Project external grounding)
#   CITRINATION_API_KEY (Citrination external grounding)

# 3. Start Memgraph
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

All 566 tests pass without external services. Tests that would require LLM API
calls or Memgraph use deterministic fakes.

## Manual end-to-end demo

### 1. Prepare the knowledge base

Place metallurgy PDF files in `knowledge_base/`:

```bash
mkdir -p knowledge_base
cp /path/to/metallurgy_pdfs/*.pdf knowledge_base/
```

Build the KB index (parses PDFs, creates FAISS index, populates Memgraph KG):

```bash
uv run hfabric index-kb
```

Output: `knowledge_base/.index/kb/` with `faiss.bin` and `chunks.json`.

### 2. Create a session

```bash
uv run hfabric new "increase Au flotation recovery by 5% without raising cyanide use"
```

This prints a session ID, e.g. `a1b2c3d4`, and creates:

```
sessions/a1b2c3d4/
  raw_files/    ← place session-specific PDFs here (optional)
  index/        ← session FAISS index (built on run)
  export/       ← output reports (written on run)
  meta.json
```

### 3. (Optional) Add session-specific documents

```bash
cp /path/to/session_pdfs/*.pdf sessions/a1b2c3d4/raw_files/
```

### 4. Run the pipeline

```bash
uv run hfabric run a1b2c3d4 "increase Au flotation recovery by 5% without raising cyanide use"
```

This:
1. Builds a session-level FAISS index from `raw_files/` (if non-empty)
2. Runs the 8-stage LangGraph pipeline: KPI parse → retrieve → generate →
   cite bind → score → constraint check → explain → export
3. Prints ranked hypotheses with claims, mechanisms, scores, justifications
4. Writes `sessions/a1b2c3d4/export/hypotheses.json` and `report.md`

### 5. Run evaluations

```bash
uv run hfabric eval a1b2c3d4
```

This runs schema validity, citation existence, and constraint pass checks on the
stored results, then re-runs the pipeline and computes Jaccard@10 determinism
score (target: ≥ 0.9).

### One-command demo script

```bash
bash scripts/demo.sh
```

This automates the full flow: start Memgraph → index KB → create session →
copy PDFs → run pipeline → eval → show report. All `hfabric` calls inside the
script use `uv run` automatically.

## Project structure

```
src/hfabric/
  cli.py                 # CLI entry point (hfabric command)
  config.py              # MVPConfig dataclass
  contracts.py           # Protocol interfaces for all modules
  schemas.py             # Pydantic models (Hypothesis, KPIParsed, etc.)
  llm.py                 # LLM factory (Yandex / RouterAI)
  embeddings.py          # SentenceTransformersProvider
  etl/                   # PDF parsing, chunking, FAISS index, KG build
  kg/                    # Memgraph KG client
  retriever/             # Query plan, vector search, KG retrieval, rerank
  generator/             # Candidate hypothesis synthesizer (LLM)
  scorer/                # Features, weighted ranker, constraint check
  explain/               # Citation bind, explain slot (LLM)
  export/                # JSON + Markdown report writer
  storage/               # SQLite session store
  session/               # SessionManager (directory structure)
  obs/                   # Logging, traces, evals
  orchestrator/          # LangGraph state graph + wiring
tests/
  test_etl/              # 84 tests
  test_kg/               # 28 tests
  test_retriever/        # 29 tests
  test_storage/          # 12 tests
  test_scorer/           # 36 tests
  test_citation/         # 10 tests
  test_generator/        # 21 tests
  test_explain_slot/     # 17 tests
  test_export/           # 11 tests
  test_obs/              # 39 tests
  test_orchestrator/     # 9 tests
  test_integration/      # 11 tests
  test_cli/              # 29 tests (incl. golden)
  golden/                # Hand-authored golden hypotheses
```

## Configuration

All knobs are in `MVPConfig` (`src/hfabric/config.py`). Key fields:

| Field | Default | Description |
|-------|---------|-------------|
| `provider` | `deepseek` | LLM provider (`yandex`/`routerai`/`proxyapi`/`deepseek`/`local`) |
| `model` | provider default | LLM model name |
| `embeddings_model` | `intfloat/multilingual-e5-small` | Sentence transformer model |
| `vector_top_k` | 20 | FAISS results per index |
| `rerank_top_k` | 8 | Chunks after rerank |
| `context_budget_tokens` | 16000 | Max tokens fed to generator |
| `citation_coverage_min` | 0.5 | FE6 coverage gate |
| `fe2_max_reprompt` | 3 | Generator retry cap |
| `memgraph_uri` | `bolt://localhost:7687` | Memgraph Bolt URI |
| `external_search` | `web` | External grounding: `none`/`web`/`web+mp`/`all` or comma list `web,mp,citrination,nims` |
| `export_format` | `json` | Export format: `json`/`docx`/`pdf`/`csv` |
| `kg_schema_path` | `None` | Optional YAML overriding KG node labels / edge types / domain patterns (R-K4 scalability) |

## Troubleshooting

**Memgraph connection error**: Ensure Docker is running and `docker compose up -d memgraph` succeeded. Check `docker compose ps`.

**LLM API error**: Verify credentials in `.env`. The `provider` field in `MVPConfig` must match the keys you provided.

**No hypotheses generated**: Check that `knowledge_base/` contains PDFs and `hfabric index-kb` ran successfully. Session `raw_files/` is optional but recommended for domain-specific evidence.

**`hfabric` command not found**: Use `uv run hfabric` to run the CLI within the project environment, or run `uv sync` to ensure the `.venv` is set up.

**HuggingFace rate-limit warning on first run**: The embeddings model (`intfloat/multilingual-e5-small`, ~120 MB) is downloaded on first use. Set `HF_TOKEN` in `.env` to avoid rate limits for faster downloads.

**Jaccard@10 below 0.9 with real LLM**: The Jaccard@10 determinism check re-runs the pipeline and compares hypothesis claims. With real LLM calls the output is non-deterministic, so scores below 0.9 are expected. The check is designed for deterministic (mocked) test runs.

## Multilingual support

The system handles PDFs in any language. Evidence chunks retain their original
language (e.g. Russian metallurgy texts), while hypotheses are generated in the
language specified by the KPI parser (defaults to English for English queries).
Citation binding uses script detection (Cyrillic vs Latin) to correctly match
cross-language references — when the claim and evidence are in different
scripts, the chunk ID reference is trusted directly.
