# Hypothesis Fabric

Hypothesis Fabric is a metallurgy research hypothesis generation pipeline.
Deterministic retrieval-first skeleton with LLM in declared slots. The
orchestrator is a LangGraph state machine; LLM works inside slots (rerank,
generate, explain, kpi_parse). Everything else is deterministic.

## Build & Test Commands

```bash
uv sync                    # install dependencies (creates .venv)
uv run pytest              # run all 336 tests (no external services needed)
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
The MVP implements all 12 at varying depth. See `MVP_DESIGN.md` for the
simplified spec and `MVP_RETROSPECTIVE.md` for gap analysis.

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

- `src/hfabric/scorer/constraint.py:constraint_check` uses a context-window
  approach (checks positive indicators near the constraint keyword).
- `src/hfabric/obs/evals.py:constraint_pass_check` previously had a simpler
  global check that produced false positives. It now mirrors the context-window
  approach, but these two implementations should be unified — `evals.py`
  should import from `scorer/constraint.py`, not reimplement.

### SessionStore initialization

- `SessionStore.init(run_id)` must be called before `set_stage_state()`.
  The orchestrator's `run()` method calls `self._store.init(run_id)`. If you
  add a new entry point that bypasses `Orchestrator.run()`, you must call
  `store.init()` yourself.

### Retriever creates LLM internally

- `Retriever.retrieve()` calls `create_chat_model()` inside the method body.
  This bypasses dependency injection. When testing or wiring, either mock
  `create_chat_model` or inject a fake retriever. Future: refactor to accept
  LLM via constructor.

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

### 3. Single source of truth for shared logic

Constraint checking logic existed in two places (`scorer/constraint.py` and
`obs/evals.py`) and diverged silently. **Never duplicate cross-module logic.
If `evals.py` needs constraint checking, import it from `scorer/constraint.py`.**

### 4. Constructor injection for all LLM-dependent components

`Retriever.retrieve()` and `generator/__init__.py:generate()` create LLM
clients internally. This makes testing harder and prevents config reuse.
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

### 7. Version-pin external services in docker-compose

Memgraph CLI flags changed between versions. **Pin the Memgraph image version
(e.g., `memgraph/memgraph:mage-2.12`) instead of `:latest` to avoid
silent breakage.**