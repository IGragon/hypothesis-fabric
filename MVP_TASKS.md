# MVP Tasks — Hypothesis Fabric (Gantt-style, worktree-parallel)

> Each task is designed so it can be developed in a **separate git worktree** and
> merged with minimal conflict. The strategy:
>
> - **Phase 0 (T0)** establishes the package skeleton + **interface contracts**
>   (pydantic schemas, `typing.Protocol`s, directory layout, full `config.py`,
>   deps). All later tasks depend on T0 only.
> - **Phase 1** tasks implement leaf modules in parallel against T0's contracts.
>   Each owns **disjoint files** and uses **fakes/stubs** for anything it
>   consumes (the real implementations live in sibling tasks and are wired in
>   Phase 2). Because each task fills pre-created stub files (not new
>   directories) and only edits files inside its own subpackage, merges stay
>   clean.
> - **Phase 2** is the single integration point that swaps fakes for reals and
>   wires the orchestrator. Sequential, depends on Phase 1.

## Gantt overview

```
Time ──►
Phase 0 [──── T0 scaffold/contracts ────]
                                     │
Phase 1 fork                         ├──> T1  ETL ────────────────────┐
                                     ├──> T2  KG service ─────────────┤
                                     ├──> T3  Retriever ─────────────┤
                                     ├──> T4  Storage (sqlite) ───────┤
                                     ├──> T5  Scorer+constraint ─────┤
                                     ├──> T6  Citation bind ─────────┤ (all 9 parallel)
                                     ├──> T7  Generator slot ─────────┤
                                     ├──> T8  Explain slot ──────────┤
                                     ├──> T9  Export writer ─────────┤
                                     └──> T10 Obs/Evals ─────────────┘
                                       Phase 2 fork                                     │
                                     ├──> T11 Orchestrator (LangGraph) (needs T0 contracts; can start in Phase 1, uses fakes)
                                     │
Phase 2 (sequential, merge gate)   [── T12 Integration ──][── T13 CLI+demo ──]
                                     depends on all T1..T11
```

T0 is the merge gate before Phase 1. T11 can start at the same time as Phase 1
(it depends only on T0 contracts). T12 starts only after **all** of T1–T11 are
merged. T13 depends on T12.

---

## Phase 0 — Foundation (sequential, blocks all)

### T0 — Scaffold, contracts, config, infrastructure

**Depends on**: nothing.
**Worktree-safe**: creates the baseline everyone forks from; no parallel partner.

**Deliverables**:
- Package layout under `src/hfabric/`:
  ```
  src/hfabric/
    __init__.py
    config.py            # full MVPConfig dataclass (all fields used by any task)
    llm.py               # migrate existing llm.py + create_chat_model
    embeddings.py        # EmbeddingsProvider Protocol + SentenceTransformersProvider
    schemas.py           # ALL shared pydantic models + TypedDicts (see below)
    contracts.py         # Protocol interfaces every module implements (see below)
    cli.py               # argparse skeleton with stubbed subcommands
    etl/{__init__.py, parser.py, chunker.py, faiss_index.py, kg_build.py, embeddings.py}
    kg/{__init__.py, client.py, schema.py, traversal.py}
    retriever/{__init__.py, query_plan.py, vector.py, kg_retrieval.py, rerank.py, budget.py}
    orchestrator/{__init__.py, state.py, nodes.py, budget.py}
    generator/{__init__.py, synth.py}
    scorer/{__init__.py, features.py, ranker.py, constraint.py}
    explain/{__init__.py, citation_bind.py, explain_slot.py}
    export/{__init__.py, writer.py}
    storage/{__init__.py, session_store.py, memgraph_persist.py}
    session/{__init__.py, manager.py}
    obs/{__init__.py, logging.py, traces.py, evals.py}
  ```
  Every file above a subpackage contains a **stub** (`raise NotImplementedError`
  or `pass`) so later tasks fill them in without creating new files.
- `pyproject.toml` updated: deps from MVP_DESIGN §9, `[tool.setuptools.packages.find]`
  pointing to `src/`.
- `docker-compose.yml`: Memgraph service (image `memgraph/memgraph`,
  `--bolt-listening-address=0.0.0.0`).
- `.env_example` extended with optional `MEMGRAPH_URI`.
- `.gitignore` extended: keep `sessions/` and `knowledge_base/` ignored (already).
- **`config.py`** — define `MVPConfig` with **all** fields from MVP_DESIGN §4.4
  so no parallel task needs to edit it. Mark which are MVP-used.
- **`schemas.py`** — shared pydantic models:
  ```python
  class KPI(BaseModel):
      metric: str; direction: str; target: str | None = None
  class KPIParsed(BaseModel):
      goal: str; kpi: KPI; constraints: list[str]; language: str
  class EvidenceChunk(BaseModel):
      chunk_id: str; doc_id: str; text: str; meta: dict
  class Hypothesis(BaseModel):
      claim: str; mechanism: str; expected_effect: str; evidence_refs: list[str]
  class ScoredHypothesis(BaseModel):
      hypothesis: Hypothesis; score: float
      features: dict[str, float]; cited_refs: dict[str, EvidenceChunk]
  class ExplainedHypothesis(BaseModel):
      scored: ScoredHypothesis
      justification: str; uncertainty: str; verification_plan: str
      graph_neighbourhood: list[str]
  class RunResult(BaseModel):
      run_id: str; session_id: str; query: str; kpi: KPIParsed
      ranked: list[ExplainedHypothesis]; export_path: str | None; status: str
  class TraceRecord(BaseModel):
      run_id: str; stage: str; slot: str | None
      token_in: int; token_out: int; latency_ms: float; status: str
  ```
  **`contracts.py`** — `Protocol`s each module exposes:
  ```python
  class ETLProtocol(Protocol): def build_index(self, source_dir, index_dir, session_id, source_kind): IndexArtifact: ...
  class KGProtocol(Protocol): def traverse(self, cypher, params) -> list[KGNode]: ...
  class RetrieverProtocol(Protocol): def retrieve(self, kpi, config, session_id) -> list[EvidenceChunk]: ...
  class GeneratorProtocol(Protocol): def generate(self, evidence, kpi, trace) -> list[Hypothesis]: ...
  class CitationProtocol(Protocol): def bind(self, hypotheses, chunks) -> tuple[list[ScoredHypothesis], float]: ...
  class ScorerProtocol(Protocol): def score(self, hypotheses, chunks, kpi, kg, config) -> list[ScoredHypothesis]: ...
  class ExplanationProtocol(Protocol): def explain(self, ranked, evidence, kg, trace) -> list[ExplainedHypothesis]: ...
  class ExportProtocol(Protocol): def export(self, result, session_id) -> str: ...
  ```
- A `tests/conftest.py` with fixtures for a tiny toy corpus, a FakeKG,
  FakeRetriever etc., usable by all parallel tasks.

**Acceptance**:
- `pip install -e .` succeeds.
- `python -c "from hfabric.config import MVPConfig; MVPConfig()"` works.
- `docker compose up -d memgraph` runs; `mgconsole` reachable.
- `pytest` imports cleanly (collects 0 tests, no import errors).
- All stub modules importable.

**Effort estimate**: M.

---

## Phase 1 — Parallel leaf modules (each in its own worktree)

> **Worktree safety rules for all Phase 1 tasks**:
> 1. Only edit files inside your **own subpackage** directory (listed in "Owns").
> 2. Never edit `config.py`, `schemas.py`, `contracts.py`, `pyproject.toml`,
>    `docker-compose.yml` — owned by T0.
> 3. For dependencies on sibling modules, import their **Protocol** from
>    `hfabric.contracts` and accept it via constructor injection; write a local
>    `Fake*` implementation in your own `tests/` for unit testing.
> 4. Do not modify top-level `cli.py` (owned by T13); wire via a registration
>    dict if needed — but in MVP modules don't self-register; T13 imports them.
> 5. Keep your tests under `tests/test_<your_module>/`.

### T1 — ETL pipeline (M1)

**Depends on**: T0. **Parallel group**: A.
**Owns**: `src/hfabric/etl/*`, `tests/test_etl/`.
**Consumes (as injected Protocol)**: `EmbeddingsProvider` (from
`hfabric.embeddings`), `KGProtocol` (from `hfabric.contracts`; use a FakeKG in
tests).

**Deliverables**:
- `parser.py`: PyMuPDF-based `parse_pdf(path) -> list[RawDoc]`.
- `chunker.py`: `RecursiveTextSplitter`-like chunker (~512 tok, 64 overlap) →
  `list[Chunk]`.
- `faiss_index.py`: build `IndexFlatIP`, L2-normalize, save `faiss.bin` +
  `chunks.json`; loader `load_faiss(index_dir)`; idempotency check on `raw_files/`
  mtimes.
- `kg_build.py`: regex + LLM-assisted entity normalisation → call
  `KGProtocol.add_entities(...)` (session-tagged).
- `etl/__init__.py`: `ETL.build_index(source_dir, index_dir, session_id,
  source_kind)` orchestrating parser→chunker→embeddings→faiss→kg.
- Implements `ETLProtocol` from contracts.
- Implement `hfabric.embeddings.SentenceTransformersProvider` (intfloat/multilingual-e5-small,
  `query:`/`passage:` prefixes).

**Acceptance**: `ETL.build_index()` on a 2-doc toy corpus produces
`faiss.bin` + `chunks.json` + calls `KGProtocol.add_entities` with correct
`session_id`/`source`. Idempotency re-run is a no-op when files unchanged.
Unit tests with FakeKG.

**Effort**: M-L.

---

### T2 — KG service (M3)

**Depends on**: T0. **Parallel group**: A.
**Owns**: `src/hfabric/kg/*`, `tests/test_kg/`.
**Consumes**: Memgraph via `gqlalchemy`/`neo4j`-driver bolt.

**Deliverables**:
- `schema.py`: node/edge type constants, property names.
- `client.py`: `MemgraphKG` connection, `add_entities`, `add_edges`, `dump(path)`,
  `load(path)`.
- `kg/__init__.py`: `KGService` implementing `KGProtocol`: `add_entities`,
  `add_edges`, `traverse(cypher, params)` (parameterised — no f-strings), helpers
  `get_entities(name)`, `neighbours(node_id, hops)`, `conflicts(source_id)`.
- `session_id`/`source` property on every node/edge; all public queries filter
  `WHERE n.session_id IN [$sid, 'kb']`.
- Persistence: `dump(path)` → `graph.json`; `load(path)` on startup.

**Acceptance**: add 3 materials+properties, traverse returns neighbours within
2 hops, session scoping hides other-session nodes, `dump`+`load` round-trips.
Parameterised Cypher only (reviewer checks no string formatting in queries).

**Effort**: M.

---

### T3 — Retriever (M2)

**Depends on**: T0. **Parallel group**: A.
**Owns**: `src/hfabric/retriever/*`, `tests/test_retriever/`.
**Consumes (injected)**: `EmbeddingsProvider`, FAISS loaders from
`hfabric.etl.faiss_index` (import the **functions**, not the ETL class — `T1`
exposes them as standalone helpers), `KGProtocol`.

**Deliverables**:
- `query_plan.py`: deterministic plan from `KPIParsed` → keyword set + `query:`
  string + KG entity-name list.
- `vector.py`: query kb + session FAISS indices, `vector_top_k` each, merge, dedup
  by `chunk_id`.
- `kg_retrieval.py`: `KGProtocol.neighbours` from matched entities, `kg_hops`,
  collect `EvidenceChunk`s with provenance.
- `rerank.py`: LLM rerank slot (uses `create_chat_model`), prompt→JSON list, FE1
  expansion (cap from config), tie-break deterministic by chunk_id.
- `budget.py`: `truncate_to_budget(evidence, tokens)` using tiktoken.
- `retriever/__init__.py`: `Retriever.retrieve(...)` implementing
  `RetrieverProtocol`.

**Acceptance**: with two fake FAISS indices (T0 conftest fixtures) and FakeKG,
`retrieve` returns ≤`rerank_top_k` chunks within token budget. FE1 retry fires
when below threshold. FE1b sets low-confidence flag.

**Effort**: M.

---

### T4 — Storage (M8)

**Depends on**: T0. **Parallel group**: A.
**Owns**: `src/hfabric/storage/*` (except `memgraph_persist.py` which T2 owns —
see conflict note), `tests/test_storage/`.
**Conflict note**: `memgraph_persist.py` is in `storage/` per T0 layout but is
logically T2's concern. **Resolution**: T2 owns `kg/client.py`'s dump/load;
T4's `storage/__init__.py` just calls `KGService.dump/load` via the Protocol. T4
does **not** edit `memgraph_persist.py` (leave T0 stub).

**Deliverables**:
- `session_store.py`: sqlite `SessionStore` with tables from MVP_DESIGN §4.3;
  methods `init(run_id)`, `save_artifact(run_id, stage, name, value_json)`,
  `load_artifact(...)`, `save_trace(...)`, `save_eval(...)`, `set_stage_state(...)`.
- `storage/__init__.py`: wraps `SessionStore` for `sessions/<id>/session.db`.

**Acceptance**: create db, save/load artifacts round-trip, trace record persisted,
stage state machine (start/done/error) works. Thread-safe (per-session).

**Effort**: S-M.

---

### T5 — Scorer + constraint check (M6 + constraint gate)

**Depends on**: T0. **Parallel group**: A.
**Owns**: `src/hfabric/scorer/*`, `tests/test_scorer/`.
**Consumes (injected)**: `KGProtocol` (for novelty feature), pydantic schemas.

**Deliverables**:
- `features.py`: `FeatureExtractor` with
  - `novelty(hyp, kg)` — avg BFS hops via `KGService.neighbours`, normalised.
  - `feasibility(hyp, constraints)` — keyword/regex match score ∈[0,1].
  - `effect(hyp, kpi)` — token overlap of `expected_effect` with `kpi.metric`/`target`.
  All normalised to [0,1].
- `ranker.py`: `WeightedRanker` — `score = Σ w_i * f_i`, fixed weights from
  `MVPConfig`, stable sort (deterministic tie-break by claim hash). Returns
  `list[ScoredHypothesis]`.
- `constraint.py`: `constraint_check(hyp, constraints)` → `{ok, violations[]}`;
  rule match (keyword/regex/boolExpr-lite); FE4 violation → Caller drops.
- Implements `ScorerProtocol`.

**Acceptance**: 5 hand-built hypotheses with fixed chunks/KG fixture →
deterministic ranked order (re-run identical). Constraint check flags a violating
hypothesis. Jaccard@10 across two runs = 1.0 (fully deterministic module).

**Effort**: M.

---

### T6 — Citation bind (M7 det part)

**Depends on**: T0. **Parallel group**: A.
**Owns**: `src/hfabric/explain/citation_bind.py`, `tests/test_citation/`.
**Consumes**: `EvidenceChunk` schema, `rapidfuzz`.

**Deliverables**:
- `bind_claims(hypotheses, chunks_map) -> tuple[list[ScoredHypothesis], float]`:
  for each `evidence_refs[i]`, verify chunk exists; fuzzy match `claim` text
  against `chunk.text` (rapidfuzz, threshold); coverage = matched/total refs.
- Coverage vs `config.citation_coverage_min` (configurable, MVP 0.5).
- Each `ScoredHypothesis.cited_refs` filled with matched `EvidenceChunk`.
- Returns coverage ratio for the FE6 gate (caller decides re-generate).

**Acceptance**: coverage gate at 0.5 lets through most MVP hypotheses; a
hypothesis with a fabricated chunk_id is flagged unmatched. Re-run identical.

**Effort**: S.

---

### T7 — Hypothesis Generator slot (M5)

**Depends on**: T0. **Parallel group**: A.
**Owns**: `src/hfabric/generator/*`, `tests/test_generator/`.
**Consumes**: `create_chat_model`, `Hypothesis` schema, `EvidenceChunk`.

**Deliverables**:
- `synth.py`: `CandidateSynthesizer` — builds prompt from evidence+KPI+constraints,
  `llm.with_structured_output(list[Hypothesis])` (matches `demo.py` pattern),
  validates non-empty `evidence_refs`, FE2 re-prompt cap from config, language
  follows `kpi.language`.
- `generator/__init__.py`: `generate(...)` implementing `GeneratorProtocol`.
- Local test stubs the LLM (returns fixed `Hypothesis` list) to verify prompt
  construction, schema validation, and FE2 retry path.

**Acceptance**: invalid-output → FE2 retry until cap; after cap, raises
`IncompleteRun` with status. Non-empty evidence_refs enforced.

**Effort**: S-M.

---

### T8 — Explain slot (M7 LLM part)

**Depends on**: T0. **Parallel group**: A.
**Owns**: `src/hfabric/explain/explain_slot.py`, `tests/test_explain_slot/`.
**Consumes**: `create_chat_model`, `KGProtocol` (for neighbourhood).

**Deliverables**:
- `explain_slot.py`: `ExplainSlot.explain(ranked, evidence_map, kg, trace)` →
  `list[ExplainedHypothesis]`. LLM prompt builds claim→evidence→mechanism→
  uncertainty→verification_plan; emits textual neighbourhood (list[str]) from
  `KGProtocol.neighbours` (ASCII/indented, no D3).
- Test with a local stub LLM returning fixed justification text + FakeKG.

**Acceptance**: every input hypothesis produces `ExplainedHypothesis` with all
fields populated and ≥1 neighbourhood line per evidence node.

**Effort**: S-M.

---

### T9 — Export writer (M9)

**Depends on**: T0. **Parallel group**: A.
**Owns**: `src/hfabric/export/*`, `tests/test_export/`.
**Consumes**: `RunResult` schema.

**Deliverables**:
- `writer.py`: `write_export(result: RunResult, session_id) -> tuple[str, str]`
  producing `sessions/<id>/export/hypotheses.json` and `sessions/<id>/export/report.md`.
  - JSON: full `RunResult.model_dump_json(indent=2)`.
  - Markdown: title, query, KPI summary table, ranked hypotheses with evidence
    quotes (verbatim chunk text), score, features, justification, uncertainty,
    verification plan, graph neighbourhood (code block).
- Idempotent: overwrites previous export for the run.

**Acceptance**: a hand-built `RunResult` writes both files; Markdown renders
readably; re-run overwrites without error.

**Effort**: S.

---

### T10 — Observability & Evals (M12)

**Depends on**: T0. **Parallel group**: A.
**Owns**: `src/hfabric/obs/*`, `tests/test_obs/`.
**Consumes**: `TraceRecord` schema, `SessionStore` Protocol.

**Deliverables**:
- `logging.py`: configure Python logging, per-stage logger, format with run_id/stage.
- `traces.py`: `TraceCollector` — wraps each slot call, records token_in/out
  (from langchain `response_metadata`/`usage_metadata`), latency_ms, status,
  writes via `SessionStore.save_trace`.
- `evals.py`: `jaccard_at_10(run_a, run_b)`, `schema_validity_check`,
  `citation_existence_check`, `constraint_pass_check`; CLI helper
  `run_evals(run_id)` producing a small eval report.

**Acceptance**: trace round-trips to sqlite; jaccard_at_10 on two identical runs
= 1.0; schema_validity flags a malformed hypothesis.

**Effort**: S-M.

---

### T11 — Orchestrator (M4)

**Depends on**: T0. **Parallel group**: A (can start alongside T1–T10).
**Owns**: `src/hfabric/orchestrator/*`, `tests/test_orchestrator/`.
**Consumes (injected)**: every `Protocol` from `contracts.py` — **the whole
point of contracts is that T11 codes against fakes**. T11 ships its own
`tests/fakes.py` implementing every Protocol with deterministic stubs.

**Deliverables**:
- `state.py`: `RunState` TypedDict (extends MVP_DESIGN §M4); `RunConfig`.
- `budget.py`: `BudgetEnforcer` — wraps LLM slot calls, truncates input to
  `context_budget_tokens`, logs truncated token counts.
- `nodes.py`: one node function per stage calling the injected Protocol; each
  persists artifacts via `SessionStore`, records a trace, handles FE1/FE2/FE4/FE6
  (loops with caps), FE5 timeout.
- `orchestrator/__init__.py`: `build_graph(protocols, config)` returns a compiled
  LangGraph `StateGraph` with edges: `kpi_parse→retrieve→generate→cite_bind→
  score→constraint_check→explain→export`, plus conditional edges for FE loops.
- A label list of returned hypotheses with FE4 filtering. Passes XB to SCORE and ALTI `_scored_alis`.
- Nothing actually real here — uses fakes for unit tests; T12 swaps in reals.

**Acceptance**: graph executes end-to-end with **all-fake** protocols producing a
`RunResult`; FE2 fires when FakeGenerator returns invalid output; FE4 drops a
violating hypothesis; FE5 timeout short-circuits to `incomplete`.

**Effort**: M-L (this is the busiest logic task — start early).

---

## Phase 2 — Integration (sequential, depends on Phase 1)

### T12 — Integration: wire real implementations

**Depends on**: T1, T2, T3, T4, T5, T6, T7, T8, T9, T10, T11 **all merged**.
**Not parallel — single merge gate.**

**Owns**: `src/hfabric/orchestrator/wiring.py` (new file — pre-created stub by T0
so no new dir), `tests/test_integration/`.

**Deliverables**:
- `build_real_orchestrator(config)` — instantiate concrete `ETL`, `MemgraphKG`,
  `Retriever`, `CandidateSynthesizer`, `CitationBind`, `Scorer`, `ExplainSlot`,
  `Exporter`, `SessionStore`, `TraceCollector`; inject into `build_graph`.
- Resolve any interface drift between T1–T11 implementations and the contracts in
  T0 (the only integration friction expected).
- End-to-end smoke test on the toy corpus: run pipeline, produce export files,
  assert ranked list non-empty, citations exist, status `complete`.

**Acceptance**: `build_real_orchestrator` runs end-to-end on the toy corpus, all
stages green, export files written, traces recorded, Jaccard@10 across two runs
≥ 0.9.

**Effort**: M (likely small because contracts absorbed most risk).

---

### T13 — CLI wiring + demo + golden eval

**Depends on**: T12.
**Owns**: `src/hfabric/cli.py`, `src/hfabric/session/manager.py`,
`tests/test_cli/`, `tests/golden/`.

**Deliverables**:
- `session/manager.py`: `SessionManager.create_session(nl_query)` →
  `sessions/<id>/{raw_files,index,export}/`, copy selected docs, persist
  `meta.json`; `get_session(id)`.
- `cli.py`:
  - `hfabric index-kb` → run T1 ETL on `knowledge_base/*` → `knowledge_base/.index/`.
  - `hfabric new "<NL query>"` → SessionManager.create_session; expects user to
    populate `raw_files/` (validates non-empty).
  - `hfabric run <session_id> "<NL query>"` → build orchestrator, invoke, print
    ranked hypotheses, export paths.
  - `hfabric eval <session_id>` → run T10 evals + Jaccard@10 re-run.
- Golden eval: 1–2 hand-authored golden hypotheses for the metallurgy corpus in
  `tests/golden/`; a check that the MVP run produces ≥1 hypothesis matching a
  golden one (heuristic similarity).
- Demo script `scripts/demo.sh` running the full scenario from MVP_DESIGN §10.

**Acceptance**: full demo on real `knowledge_base/` PDFs succeeds; ranked
hypotheses printed; export files readable; Jaccard@10 ≥ 0.9.

**Effort**: M.

---

## Parallelism summary

| Phase | Tasks | Parallelisable? |
|-------|-------|-----------------|
| 0 | T0 | No (foundation) |
| 1 | T1–T11 | **Yes — all 11 in parallel worktrees** |
| 2 | T12 | No (depends on all Phase 1) |
| 2 | T13 | No (depends on T12) |

Total task count: 14. Critical path length: T0 → (any of T1–T11) → T12 → T13.
Wall-clock optimised by maximising Phase 1 width (11 parallel worktrees).

---

## Risk register (per-task) and coupling list

- **T1↔T3**: T3 imports `load_faiss` helpers from T1's `etl.faiss_index`. If T1
  renames, T3 breaks after merge but not at compile time (imports are deferred
  inside functions). Mitigation: T0 declares the function signatures in
  `etl/faiss_index.py` stub.
- **T1↔T2**: T1 calls `KGProtocol.add_entities`. Both must honour the contract;
  T0 owns the contract so no merge conflict, only semantic drift risk for T12 to
  reconcile.
- **T4↔T2**: see conflict note in T4 (memgraph_persist.py).
- **T11↔All**: T11 codes against Protocols only; real wiring is T12. Lowest
  coupling if T0's contracts are complete.

### Things explicitly NOT in the MVP tasks

- M10 Feedback Loop (cut)
- LLM Judge in M6 (cut — FE3 path)
- Gap Finder slot #10 (cut)
- Canvas re-run F14 (cut)
- Web UI (cut)
- Jira/YouTrack / roadmap export (cut)
- OTel (cut)
- Multi-domain KG schema extension R-K4 (cut)
- External scientific APIs (cut)

These can be added in a "MVP+1" task list after the MVP demo passes.