# MVP Retrospective — Hypothesis Fabric

> Retrospective on the MVP implementation (T0–T13) against the full system
> design (`docs/system-design.md`, `docs/specs/`, `MVP_DESIGN.md`).

---

## 1. Summary of work done

### Tasks completed

| Phase | Task | Module | Tests | Status |
|-------|------|--------|-------|--------|
| 0 | T0 | Scaffold, contracts, config, infrastructure | — | Done |
| 1 | T1 | ETL pipeline (parser, chunker, FAISS, KG build) | 84 | Done |
| 1 | T2 | KG service (Memgraph client, traversal, dump/load) | 28 | Done |
| 1 | T3 | Retriever (query plan, vector search, KG retrieval, rerank) | 29 | Done |
| 1 | T4 | Storage (SQLite session store) | 12 | Done |
| 1 | T5 | Scorer + constraint check | 36 | Done |
| 1 | T6 | Citation bind (rapidfuzz) | 10 | Done |
| 1 | T7 | Hypothesis generator slot | 21 | Done |
| 1 | T8 | Explain slot (LLM + KG neighbourhood) | 17 | Done |
| 1 | T9 | Export writer (JSON + Markdown) | 11 | Done |
| 1 | T10 | Observability & evals | 39 | Done |
| 1 | T11 | Orchestrator (LangGraph state graph) | 9 | Done |
| 2 | T12 | Integration wiring | 11 | Done |
| 2 | T13 | CLI, session manager, golden eval, demo script | 29 | Done |

**Totals**: 14 tasks, 336 tests, ~4,300 lines of source code, ~6,100 lines of
test code. All tests pass. End-to-end pipeline verified on real metallurgy
PDFs (5 documents, 633 KB chunks, 360 session chunks, 3–4 ranked hypotheses
per run).

### What the MVP delivers

A working CLI tool (`hfabric`) that:
1. Indexes a knowledge base of metallurgy PDFs (PyMuPDF → chunks → FAISS → Memgraph KG).
2. Creates per-session workspaces with optional ad-hoc documents.
3. Runs an 8-stage LangGraph pipeline: KPI parse → retrieve → generate →
   cite_bind → score → constraint_check → explain → export.
4. Produces ranked hypotheses with claims, mechanisms, evidence citations,
   scores, justifications, uncertainty estimates, and verification plans.
5. Exports JSON + Markdown reports.
6. Runs evals (schema validity, citation coverage, constraint pass, Jaccard@10).

---

## 2. What went well

### Contract-first development

T0 defined Protocol interfaces (`contracts.py`) and Pydantic schemas
(`schemas.py`) before any implementation. This allowed all 11 Phase 1 tasks
to proceed in parallel against fakes/stubs. T12 integration was nearly
friction-free — only two adapter classes needed (citation, export) and one
interface drift fix (`store.init()` call in the orchestrator).

**Continue this practice.** Contract-first with Protocol injection is the
single biggest reason Phase 1 parallelized cleanly.

### Test discipline

Every module shipped with unit tests using deterministic fakes. The 336-test
suite runs without Memgraph, LLM API keys, or network access. Test-to-code
ratio is ~1.4:1. No flaky tests. The integration test (T12) caught a real
`store.init()` bug that would have broken every production run.

**Continue this practice.** High test ratio with deterministic fakes is the
only way to keep a 12-module system mergeable.

### Deterministic-first architecture

The "LLM in slots only" philosophy (AD-4) proved its value. When the LLM
produces different hypotheses each run (non-deterministic Jaccard@10), the
deterministic backbone (retrieval, scoring, citations, constraints, export)
still produces valid, traceable, structured output. The system degrades
gracefully — it never breaks, just varies.

**Continue this practice.** Keeping LLM calls isolated to declared slots with
deterministic fallbacks (FE3 path) is the right architectural stance.

### Parallel worktree strategy

The Gantt-style task breakdown (T0 → T1–T11 parallel → T12 → T13 sequential)
worked as designed. Phase 1 tasks touched disjoint file sets. No merge
conflicts occurred during the entire implementation.

**Continue this practice.** Disjoint-file-ownership task decomposition is
effective for teams of any size.

### langchain-structured-output pattern

Using `llm.with_structured_output(HypothesisList)` for generation and
`llm.with_structured_output(KPIParsed)` for KPI parsing worked reliably with
the Yandex provider. Schema validation at the LLM boundary (FE2 retry) caught
malformed output and re-prompted successfully.

**Continue this practice.** Structured output with validation + retry is the
correct pattern for LLM slots in a deterministic framework.

---

## 3. What went bad

### No integration test until T12

T11 (orchestrator) was tested with fakes only. The first real integration
(T12) exposed a `SessionStore.init()` gap — the orchestrator called
`set_stage_state()` (UPDATE-only) without first calling `init()` (INSERT),
silently producing empty stage-state rows. This could have been caught earlier
with an integration test after T4 (storage).

**Do not continue this practice.** Each module that depends on another module's
stateful API should have an integration test verifying the cross-module lifecycle.

### Memgraph version drift

The `docker-compose.yml` used `--bolt-listening-address`, which was removed in
recent Memgraph versions. The Cypher `MATCH (n)-[*1..$hops]-(m)` pattern (with
parameterized relationship depth) is not supported by Memgraph, causing a
runtime crash in `neighbours()`. Both bugs were only caught during manual
end-to-end testing — unit tests used `FakeMemgraphKG`.

**Do not continue this practice.** Integration tests against real Memgraph
(even via testcontainers) should exist for the KG module to catch dialect-specific
issues.

### Multilingual citation binding gap

`bind_claims` used `rapidfuzz.token_sort_ratio` between English hypothesis claims
and Russian evidence chunks, scoring near 0% and producing empty `cited_refs`.
The fix (script detection + chunk_id trust for cross-script pairs) was
discovered only during manual testing with real PDFs. All 10 citation unit
tests used same-language fixtures and passed despite the bug.

**Do not continue this practice.** Test fixtures must include multilingual
scenarios when the system is designed for multilingual use.

### LLM non-determinism unhandled for Jaccard@10

The `hfabric eval` command re-runs the pipeline and computes Jaccard@10,
expecting ≥ 0.9. With real LLM calls, different hypotheses are generated each
run, producing Jaccard@10 = 0.0. The MVP has no mechanism for deterministic
LLM output (no temperature=0, no caching, no seed). This makes the eval
metric meaningless in production.

**Do not continue this practice.** Either set `temperature=0` and cache LLM
responses, or reframe Jaccard@10 as a test-only metric (not a production eval).

### Constraint check had two divergent implementations

`scorer/constraint.py:constraint_check` used a context-window approach (±50 chars
around the constraint keyword). `obs/evals.py:constraint_pass_check` used a
global "any positive indicator anywhere" check. The latter produced false
positives — flagging "increase recovery" as violating "no cyanide increase".
Two implementations of the same logic diverged silently.

**Do not continue this practice.** Constraint checking logic must live in one
place. `obs/evals.py` should import from `scorer/constraint.py`, not
reimplement it.

### Retriever creates its own LLM internally

`Retriever.retrieve()` calls `create_chat_model()` inside the method body,
creating a new LLM client on every retrieval. This bypasses DI, makes testing
harder (must mock `create_chat_model`), and prevents LLM config reuse. The
same pattern exists in `generator/__init__.py:generate()`.

**Do not continue this practice.** All LLM-dependent components should accept
the LLM via constructor injection, not create it internally.

---

## 4. Overall results

| Metric | Target | Achieved | Notes |
|--------|--------|----------|-------|
| Tests passing | 100% | 336/336 | All green |
| Stages executed | 8/8 | 8/8 | KPI parse → export |
| Hypotheses per run | 3–7 | 3–4 | LLM-dependent, within range |
| Citation coverage | ≥ 50% (MVP) | 100% | After cross-script fix |
| Schema validity | 100% | 100% | All hypotheses pass schema check |
| Constraint pass | 100% | 100% | After context-aware fix |
| Jaccard@10 | ≥ 0.9 | 0.0 (real LLM) | Expected with non-deterministic LLM |
| Export files | JSON + MD | JSON + MD | Both written, readable |
| Traces recorded | All stages | All stages | SQLite traces table populated |
| Artifacts persisted | All stages | All stages | SessionStore verified |

The MVP delivers a functional end-to-end pipeline. The happy path works on
real metallurgy PDFs, producing domain-relevant hypotheses with citations.
The gaps are in non-functional requirements (determinism, latency, cost
control) and in features explicitly cut from the MVP scope.

---

## 5. Practices to continue

1. **Contract-first development** — Protocols + schemas before implementation.
2. **Deterministic-first architecture** — LLM in declared slots only.
3. **High test-to-code ratio with deterministic fakes** — ~1.4:1, no external dependencies.
4. **Disjoint-file-ownership task decomposition** — enables parallel development.
5. **Structured output at LLM boundaries** — with validation + retry (FE2).
6. **SQLite session store for artifacts/traces** — simple, auditable, re-runnable.

## 6. Practices to discontinue

1. **Reimplementing the same logic in two places** (constraint check in scorer vs evals).
2. **Creating LLM clients inside method bodies** instead of constructor injection.
3. **Same-language-only test fixtures** for a multilingual system.
4. **Testing only with fakes against stateful cross-module APIs** (SessionStore.init).
5. **Expecting deterministic Jaccard@10 from non-deterministic LLM** without temperature/cache.
6. **Using a hardcoded Memgraph CLI flag** without a version-pin or integration test.

---

## 7. Gap analysis: MVP → full system design

Below is a module-by-module summary of what the MVP implements vs what the
full design (`docs/specs/`) specifies, and what needs to be updated to close
the gap.

### M1 — Ingestion & ETL (`etl/`)

**MVP state**: PyMuPDF parser, sliding-window chunker, FAISS `IndexFlatIP`,
regex-based entity extraction, idempotent index rebuild, `SentenceTransformersProvider`.

**Gaps to close**:
- Add LLM-assisted entity refinement/normalization slot (currently regex-only).
- Add `contradicts` edge detection at ETL time (source conflict surfacing).
- Add dead-letter queue + retry for failed ETL jobs (FE9).
- Add GROBID + SciSpaCy parsers for scientific PDFs (currently generic PyMuPDF).
- Add Excel/DB parsers for tabular data.
- Add ISA-Tab/Allotrope metadata schema support.
- Performance: verify ≤ 2h batch latency on 10⁴ docs (currently untested at scale).

### M2 — Retriever (`retriever/`)

**MVP state**: Deterministic query plan, dual FAISS search (kb + session), KG
traversal, LLM rerank, token budget truncation, FE1 expansion.

**Gaps to close**:
- Add document deny-list support (forbidden docs filtered from results).
- Add external API search toggle (currently none).
- Add FE1b path: empty results → low-confidence flag + data-collection plan.
- Add rerank-delta metric (measure LLM rerank impact vs original order).
- Accept LLM via constructor injection (currently creates internally).
- Add SPARQL support for KG traversal (currently Cypher only).

### M3 — Knowledge Graph Service (`kg/`)

**MVP state**: Memgraph client, session-scoped queries, BFS traversal,
dump/load, parameterized Cypher.

**Gaps to close**:
- Add `contradicts` edge detection and conflict-aware queries (FE7).
- Add schema extensibility for new domains (polymers/composites) without core rework.
- Add snapshot-based resync on KG/index desync (FE9 path).
- Add graph-distance novelty scoring as a first-class KG API (currently computed in scorer).
- Add `measured_as` and `composed_of` edge usage (currently only `influences` is emitted).
- Add provenance date/author/conditions on edges (currently only chunk_id/doc_id).

### M4 — Orchestrator (`orchestrator/`)

**MVP state**: LangGraph `StateGraph`, 8 nodes, conditional edges for FE2/FE4/FE6
loops, `BudgetEnforcer`, `Orchestrator.run()` entry point.

**Gaps to close**:
- Add Canvas re-run capability (R-F14) — edit an artifact, re-run from that stage.
- Add per-stage timeout enforcement (FE5) — currently timeouts are in config but not enforced.
- Add FE1 evidence-sufficiency gate with query expansion loop.
- Add FE5 partial-result emission with `incomplete` status on timeout.
- Add KPI/Task Parser as a proper LLM slot with structured output validation (currently bare).

### M5 — Hypothesis Generator (`generator/`)

**MVP state**: `CandidateSynthesizer` with `with_structured_output`, FE2 retry,
prompt construction from evidence + KPI + constraints.

**Gaps to close**:
- Add Novelty Gap Finder slot (#10) — generates hypotheses from KG knowledge gaps.
- Add counterfactual and analogy-based generation modes.
- Add multilingual output enforcement (currently follows KPI language but not strictly verified).
- Accept LLM via constructor injection in module-level `generate()` function.
- Add 15s timeout enforcement on generation.

### M6 — Scorer / Ranker (`scorer/`)

**MVP state**: Deterministic features (novelty, feasibility, effect),
`WeightedRanker` with config weights, `constraint_check` with context-window logic.

**Gaps to close**:
- Add LLM Judge slot for qualitative scoring (FE3 path — currently always det-only).
- Add risk axis (R-OUT6) and realizability axis as separate features.
- Add weight calibration from feedback labels (M10 loop) — currently fixed weights.
- Add rank-stability enforcement (Jaccard@10 ≥ 0.9) with deterministic mode.
- Remove duplicate constraint_check from `obs/evals.py` — import from `scorer/constraint.py`.

### M7 — Justification & Explanation (`explain/`)

**MVP state**: `bind_claims` with cross-script citation matching, `ExplainSlot`
with LLM-generated justification/uncertainty/verification + KG neighbourhood.

**Gaps to close**:
- Raise citation coverage gate from 50% (MVP) to 85% (production, R-K2).
- Add hallucination-source rate tracking (≤ 4%, R-K2).
- Add FE7 conflict-aware citation selection (choose reliable source, store alternative).
- Add deterministic visualization renderer for relationship graph (currently text-only).
- Add structured 5-step explanation template enforcement (currently free-form LLM).

### M8 — Memory & Context (`storage/`, `session/`)

**MVP state**: SQLite `SessionStore` (stage_state, artifacts, traces, evals),
`SessionManager` for directory structure, `BudgetEnforcer` for token truncation.

**Gaps to close**:
- Add Feedback Labels Store (long-term, accepted/rejected/adjusted) for weight calibration.
- Add Canvas state model (editable artifacts, re-run without loss).
- Add context budget enforcement per slot (currently only in retriever, not all slots).
- Add log redaction (no raw source text in logs/metrics, R-N5).
- Add GDPR-equivalent deletion support for stored data.

### M9 — Export & Integration (`export/`)

**MVP state**: `write_export` producing `hypotheses.json` + `report.md`.

**Gaps to close**:
- Add PDF/DOCX report generation (currently JSON + Markdown only).
- Add CSV/JSON task export.
- Add Jira/YouTrack REST API integration (POST create tasks).
- Add optional roadmap constructor (R-OUT8).
- Add RBAC on export.
- Add field-level redaction for confidential output.
- Add idempotency via external ID (prevent duplicate tracker tasks).
- Add report-template versioning + tracker-version compatibility.

### M10 — Expert Feedback Loop (not implemented)

**MVP state**: Cut entirely. Fixed scorer weights, no labels store.

**Gaps to close**:
- Implement full feedback loop: expert labels → M8 store → M6 weight calibration.
- Add multi-expert conflict handling (store both labels, flag, audit).
- Add audit trail of label changes.
- Add on-request deletion under privacy rules.
- Ensure no LLM fine-tuning (ASSUM-7) — weight re-weighting only.

### M11 — Serving & Config (`config.py`, `llm.py`, `cli.py`)

**MVP state**: `MVPConfig` dataclass, Yandex/RouterAI LLM factory, CLI with
4 subcommands, `.env` loading.

**Gaps to close**:
- Add API Gateway (REST API) — currently CLI only.
- Add on-prem LLM runtime isolation (currently external API calls).
- Add dual operational modes: "strict confidentiality" (external off) vs "extended search".
- Add LLM + slot-schema versioning with A/B switching.
- Add regression evals (M12) triggered on model change.
- Add centralized secret management (currently plain `.env`).
- Add ETL batch scheduling (Airflow/Prefect) — currently manual `hfabric index-kb`.
- Add K8s/Docker deployment manifests (currently single docker-compose for Memgraph only).

### M12 — Observability & Evals (`obs/`)

**MVP state**: Python logging, `TraceCollector` with token counts + latency,
evals (Jaccard@10, schema validity, citation existence, constraint pass).

**Gaps to close**:
- Add OpenTelemetry spans per stage and per LLM slot (currently Python logging only).
- Add golden citations and golden rankings datasets (currently golden hypotheses only).
- Add novelty diversity metric.
- Add rank-stability regression runs on model/weight changes.
- Add log redaction (no raw source text in traces/metrics).
- Add audit log of FE4 discards and label conflicts.
- Add latency/cost dashboards (p50/p95, tokens/session).
- Add API availability monitoring (≥ 99.5%).

---

## 8. Suggested priority for post-MVP work

| Priority | Module | What | Why |
|----------|--------|------|-----|
| P0 | M6 | Set `temperature=0` or cache LLM responses | Jaccard@10 is broken without determinism |
| P0 | M6 | Unify constraint_check (remove duplicate in evals) | Correctness bug risk |
| P0 | M2 | Inject LLM into Retriever via constructor | Testability + config reuse |
| P1 | M8 | Add Feedback Labels Store | Unblocks M10 calibration loop |
| P1 | M11 | Add REST API (FastAPI) | Unblocks UI and programmatic access |
| P1 | M12 | Add OpenTelemetry spans | Production observability |
| P1 | M9 | Add DOCX/PDF export | User-facing deliverable format |
| P2 | M10 | Implement feedback loop → weight calibration | Product metric R-A3 |
| P2 | M4 | Add Canvas re-run (R-F14) | User interactivity |
| P2 | M5 | Add Novelty Gap Finder slot | Hypothesis quality R-OUT4 |
| P2 | M3 | Add `contradicts` edge detection | Source conflict awareness (FE7) |
| P3 | M11 | Add on-prem LLM runtime | R-N5 compliance |
| P3 | M9 | Add Jira/YouTrack integration | R-F13 |
| P3 | M12 | Add golden citations + rankings datasets | Regression coverage |