# Hypothesis Fabric

Hypothesis Fabric is a metallurgy research hypothesis generation pipeline.
Deterministic retrieval-first skeleton with LLM in declared slots. The
orchestrator is a LangGraph state machine; LLM works inside slots (rerank,
generate, explain, kpi_parse). Everything else is deterministic.

## Build & Test Commands

```bash
uv sync                    # install dependencies (creates .venv)
uv run pytest              # run all 566 tests (no external services needed)
uv run pytest tests/test_orchestrator/   # run a specific module
uv run pytest -v           # verbose output
uv run hfabric index-kb    # build KB index from knowledge_base/ PDFs
uv run hfabric new "<query>"            # create a session
uv run hfabric run <session_id> "<query>"  # run the pipeline
uv run hfabric eval <session_id>       # run evals + Jaccard@10
```

No lint or typecheck commands are configured yet. Python 3.13+ required.

## Architecture

The system is split into 12 modules (M1–M12) per `docs/system-design.md`.
The MVP implements all 12 at varying depth. Gap analysis lives in the
"Gotchas and known issues" and "What to consider in the future" sections below.

### Core design principles

1. **Contract-first**: `src/hfabric/contracts.py` defines Protocol interfaces
   for every module. `src/hfabric/schemas.py` defines all Pydantic models.
   These are the single source of truth — do not edit them without updating
   all dependents.
2. **Deterministic-first**: LLM calls are isolated to declared slots (kpi_parse,
   rerank, generate, explain). Everything else is deterministic Python. The
   system must produce valid structured output even if the LLM returns garbage.
3. **Constructor injection**: All modules accept their dependencies via
   `__init__` as Protocol types from `hfabric.contracts`. Never create
   dependencies inside method bodies.
4. **No comments**: Do not add comments to code unless explicitly requested.

### Pipeline stages (LangGraph)

```
kpi_parse → retrieve → generate → cite_bind → score → constraint_check → explain → export
```

Each stage is a node factory in `orchestrator/nodes.py`. Conditional edges
handle FE2 retry (generate loops), FE4 drops (constraint violation → skip),
and FE6 retry (low citation coverage → regenerate).

### Key files

- `src/hfabric/contracts.py` — Protocol interfaces (do not edit casually)
- `src/hfabric/schemas.py` — Pydantic models (do not edit casually)
- `src/hfabric/config.py` — MVPConfig dataclass with all knobs
- `src/hfabric/orchestrator/__init__.py` — build_graph + Orchestrator class
- `src/hfabric/orchestrator/nodes.py` — 8 node factories + serialization
- `src/hfabric/orchestrator/wiring.py` — build_real_orchestrator (T12 integration)
- `src/hfabric/cli.py` — CLI entry point

## Conventions

### Code style

- No comments in code unless explicitly requested.
- Use `from __future__ import annotations` at the top of every module.
- Follow the existing adapter pattern: wrap free functions (like `bind_claims`,
  `write_export`) in small adapter classes to satisfy Protocol interfaces.
- Pydantic models for all data crossing module boundaries.
- Serialize Pydantic models to dicts before storing in LangGraph state
  (LangGraph state must be JSON-serializable).

### Testing

- Every module ships with unit tests using deterministic fakes.
- Test files live in `tests/test_<module>/`.
- Shared fakes are in `tests/test_orchestrator/fakes.py`.
- The full test suite runs without Memgraph, LLM API keys, or network access.
- `uv run pytest` is the only command needed — never use bare `pytest` (it
  may pick up a system-level pytest that can't find the `hfabric` package).

### Protocol adherence

When implementing a new module, check `contracts.py` for the exact method
signatures. The orchestrator nodes call methods by these signatures. If a
module's return type differs from the Protocol's annotation (e.g.
`Retriever.retrieve` returns `dict` not `list[EvidenceChunk]`), the orchestrator
nodes handle the drift — but do not introduce new drift without updating nodes.

## Gotchas and known issues

### Memgraph

- The Docker image uses `--bolt-address=0.0.0.0`, NOT
  `--bolt-listening-address` (removed in Memgraph v2+).
- Memgraph does not support parameterized relationship depth in Cypher:
  `MATCH (n)-[*1..$hops]-(m)` fails with "Property map matching not supported".
  Interpolate the integer directly: `f"[*1..{hops}]"`.
- The KG module's unit tests use `FakeMemgraphKG` — Memgraph dialect issues
  are only caught during manual integration testing.

### Multilingual content

- The knowledge base PDFs are in Russian; hypothesis claims are generated in
  English (per KPI parser language field). Citation binding uses script
  detection (Cyrillic vs Latin) — when claim and chunk text are in different
  scripts, the chunk_id reference is trusted directly without fuzzy text match.
- Test fixtures MUST include multilingual scenarios. Same-language-only fixtures
  will pass despite cross-language bugs.

### LLM non-determinism

- The Yandex/RouterAI LLM produces different hypotheses on each run.
  `Jaccard@10` will be 0.0 with real LLM calls. This is expected.
  The metric is meaningful only with deterministic (mocked) LLM.
- Future: set `temperature=0` or cache LLM responses to achieve determinism.

### Duplicate constraint logic

- Constraint checking is unified in `src/hfabric/scorer/constraint.py`
  (`constraint_satisfied`/`constraint_check`). `obs/evals.constraint_pass_check`
  and `scorer/features.extract_feasibility`/`extract_realizability` both import
  and reuse the single implementation. Do not reimplement this logic elsewhere.

### SessionStore initialization

- `SessionStore.init(run_id)` must be called before `set_stage_state()`.
  The orchestrator's `run()` method calls `self._store.init(run_id)`. If you
  add a new entry point that bypasses `Orchestrator.run()`, you must call
  `store.init()` yourself.

### Retriever requires LLM via constructor injection

- `Retriever.__init__` accepts `llm=...`. `Retriever.retrieve()` raises
  `RuntimeError` if no LLM was injected — it no longer silently creates one.
  `build_real_orchestrator` always injects the LLM. The convenience
  `generator/__init__.py:generate()` accepts an `llm=` override too.

### HuggingFace embeddings download

- The sentence-transformers model (`intfloat/multilingual-e5-small`, ~120 MB)
  is downloaded on first use. Set `HF_TOKEN` in `.env` to avoid rate limits.

## What to consider in the future to mitigate mistakes

### 1. Add integration tests for external dependencies

The KG module was only tested with `FakeMemgraphKG`. Real Memgraph had two
dialect-specific bugs (CLI flag, parameterized depth) that weren't caught
until manual testing. **Add integration tests using testcontainers or a
CI Memgraph service.**

### 2. Multilingual test fixtures

All citation bind unit tests used English-vs-English text. The cross-language
citation bug (English claims, Russian chunks) wasn't caught. **Add fixtures
with mixed-script content (English claims + Russian chunks) to every test
module that processes text.**

### 3. Single source of truth for shared logic (DONE)

Constraint checking is now unified; `evals.py` and `features.py` import from
`scorer/constraint.py`. **Never duplicate cross-module logic.**

### 4. Constructor injection for all LLM-dependent components (DONE)

`Retriever` now strictly requires LLM via `__init__` (raises otherwise).
`generator/__init__.py:generate()` accepts `llm=` and `config=` overrides.
**All LLM-dependent components must accept the LLM via `__init__`, not create
it inside method bodies.**

### 5. Deterministic LLM mode for production evals

`Jaccard@10` is meaningless with non-deterministic LLM output. **Set
`temperature=0` on LLM calls, or implement response caching, or reframe
Jaccard@10 as a test-only metric (not a production eval).**

### 6. Test cross-module lifecycle assumptions

The `SessionStore.init()` gap (UPDATE without INSERT) wasn't caught because
T11 only tested with fakes. **Each module that depends on another module's
stateful API should have an integration test verifying the cross-module
lifecycle.**

### 7. Version-in external services in docker-compose

Memgraph CLI flags changed between versions. **Pin the Memgraph image version
(e.g., `memgraph/memgraph:mage-2.12`) instead of `:latest` to avoid
silent breakage.**

## Completed improvements (gap closure)

The following gaps were addressed:

- **Feedback loop (E7)**: `FeedbackStore` now persists per-label features;
  `scorer.calibration.apply_feedback_weights` reads labels and calibrates the
  `WeightedRanker` weights at `Scorer` construction. `build_real_orchestrator`
  injects the session `FeedbackStore` into the Scorer. The API `/feedback`
  endpoint auto-attaches features from the run's `hypotheses.json`.
- **External grounding (E8)**: `retriever/external.py` adds real HTTP-based
  `citrination_search` and `nims_matnavi_search` (graceful degradation). Mode
  `external_search` accepts comma-separated sources (`web,mp,citrination,nims`)
  or legacy `web`/`web+mp`/`all`/`none`. UI exposes all four source checkboxes.
- **Export formats (R-F12/F13/E6)**: added `export/pdf_writer.py` (reportlab),
  `export/csv_writer.py`, `export/youtrack.py`. CLI `--format` supports
  `json`/`docx`/`pdf`/`csv`; CLI `--jira`/`--youtrack` now perform real exports.
  API `/export`, `/export/download`, `/export/jira`, `/export/youtrack` exposed.
- **Example pre-made outputs (E1)**: `/examples` extracts and returns the
  expert-authored hypothesis `.docx` text for each `Пример N`; the UI renders
  it in an expander.
- **KG schema config-driven (R-K4)**: `kg/schema.py` exposes
  `DEFAULT_NODE_LABELS`/`DEFAULT_EDGE_TYPES`/`DEFAULT_DOMAIN_PATTERNS` and
  `load_schema(path)` (YAML merge). `MVPConfig.kg_schema_path` selects a
  domain YAML; `MemgraphKG` indexes/validates configured labels; `kg_build`
  uses schema patterns. New domains connect without core rebuild.
- **Dead-code purge**: removed unused `orchestrator/budget.py::BudgetEnforcer`
  and `storage/memgraph_persist.py`; dropped the never-read
  `MVPConfig.model_registry` field (the `ModelRegistry` class + its test remain).
- **obs/redaction.py**: `redact_text` now substitutes source patterns (the
  previous loop body was a no-op).
- **API `/eval`**: now calls the real `obs.evals.run_evals` instead of
  returning hardcoded metrics (per-run route `/runs/{run_id}/eval` plus a
  backward-compatible `/sessions/{id}/eval` alias).
- **Tests**: added `test_retriever/test_external.py`, `test_scorer/test_scorer_feedback_loop.py`,
  `test_export/{test_csv,test_pdf,test_youtrack}.py`, `test_kg/test_schema.py`,
  `test_session/test_manager.py`, `test_scorer/test_constraint_multilingual.py`,
  `test_api/{test_examples,test_eval}.py`. Test count: 566.

### Remaining future work (still open)

- Memgraph integration tests via testcontainers/CI (item 1 above).
- `temperature=0` is already set in `MVPConfig`; LLM response caching optional
  for stronger determinism (item 5).
- Cross-script constraint matching (RU-constraint vs EN-claim) has no synonym
  bridge; same-script constraints are enforced. `LLMJudge` and the LLM gap
  finder path are implemented but currently unused in the default wiring.