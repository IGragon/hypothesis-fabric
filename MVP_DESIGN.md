# MVP Design — Hypothesis Fabric (vertical happy-path slice)

> Simplified, demo-ready subset of the full system described in `docs/`.
> Faithful to the V2 architecture (deterministic retrieval-first skeleton + LLM in
> slots) on the **happy path**; advanced features are stubbed or cut.

---

## 1. Scope and position relative to the full design

The full system (`docs/system-design.md`) defines 12 modules (M1–M12), an
11-stage workflow, on-prem LLM, Neo4j KG, canvas re-run, expert feedback
calibration, Jira export, web UI, and OTel observability. The MVP keeps the
**end-to-end happy path** (every stage runs once) and the **LLM-in-slots +
deterministic-carcade** philosophy, but simplifies the components.

| Aspect | Full design | MVP |
|--------|-------------|-----|
| Modules | M1–M12 | All present, several simplified |
| ETL | Prebuilt once globally (AD-2) | **Two-tier**: global `knowledge_base/` index **+** per-session `raw_files/` index |
| Vector DB | VectorDB (Redis/Postgres+pgvector/Qdrant) | **FAISS** (one index per source) |
| Graph DB | Neo4j | **Memgraph** (Apache-2.0, Cypher) |
| Embeddings | Multilingual RU/EN/CN | **`intfloat/multilingual-e5-small`** (384-d, local) |
| LLM runtime | On-prem isolated | Existing **Yandex/RouterAI** LangChain setup (R-N5 relaxed for MVP) |
| Orchestrator | State machine + canvas re-run (F14) | LangGraph `StateGraph`, **linear**; no canvas re-run |
| Generator | Synthesizer + Gap Finder (#9, #10) | **Candidate Synthesizer only**; Gap Finder cut |
| Scorer | det features + **LLM Judge** + weighted ranker | **det features + weighted ranker** (LLM Judge cut, FE3 det-only path) |
| Feedback | Labels Store + weight calibration (M10) | **Cut**; fixed weights |
| Export | PDF/DOCX/CSV/JSON + Jira/YouTrack + roadmap | **JSON + Markdown** only |
| UI | React canvas | **Cut**; CLI only |
| Obs | OTel + evals | Python logging + token counts + 1–2 golden + Jaccard@10 |

### Hard cuts (out of MVP)

- M10 Expert Feedback Loop — fixed weights, no labels store.
- LLM Judge in M6 — always the FE3 deterministic-only path.
- Novelty Gap Finder slot (#10) — only Candidate Synthesizer (#9).
- Canvas / stage re-run (F14 / AD-6) — single linear run.
- Web UI (Container 1) — CLI only.
- Jira/YouTrack REST export, roadmap builder — file export only.

---

## 2. Architecture overview

```
                         CLI (hfabric)
                              │
            ┌─────────────────┼─────────────────┐
            │                 │                 │
       index-kb            new <query>      run <id> <query>
            │                 │                 │
            ▼                 ▼                 ▼
    ┌──────────────┐  ┌──────────────┐  ┌────────────────────────────┐
    │ Global ETL   │  │ Session mgr  │  │ Orchestrator (LangGraph)    │
    │ (knowledge_  │  │ create dirs, │  │  KPI parse → retrieve →      │
    │  base/.index)│  │ copy docs    │  │  generate → cite_bind →     │
    └──────┬───────┘  └──────┬───────┘  │  score → constraint →       │
           │                 │          │  explain → export            │
           │                 ▼          └────────────────────────────┘
           │          per-session ETL
           │          (sessions/<id>/index)
           │                 │
           ▼                 ▼
   ┌───────────────────────────────────┐
   │  FAISS (kb) + FAISS (session)      │
   │  Memgraph (source="kb" +           │
   │   source="session", session_id)    │
   └───────────────────────────────────┘
                 ▲
                 │ retrieve
   ┌─────────────┴────────────┐
   │ LLM slots (Yandex/Router)│  rerank, generate, explain, kpi_parse
   └──────────────────────────┘
```

---

## 3. Two-tier index model

The full design (AD-2) builds one global index from the knowledge base. The MVP
extends this with a **per-session index** so a user can attach ad-hoc documents
to a run.

```
knowledge_base/
  *.pdf                      # the curated global corpus
  .index/
    faiss.bin                # global vector index (prebuilt once)
    chunks.json              # chunk_id → {text, meta, source}
    embeddings_model.txt     # model name used (for reproducibility)

sessions/
  <session_id>/
    raw_files/               # user-provided docs for this run; NON-EMPTY
    index/
      faiss.bin              # per-session vector index (cached)
      chunks.json
      graph.json             # Memgraph dump for this session
    session.db               # sqlite: stage_state, artifacts, traces, tokens
    export/
      report.md
      hypotheses.json
    meta.json                # {nl_query, created_at, kpi_parsed}
```

- **Global index** is built once via `hfabric index-kb` and reused by all runs.
- **Per-session index** is built from `raw_files/` and **cached**: ETL is skipped
  if `sessions/<id>/index/faiss.bin` exists (and `raw_files/` mtimes are
  unchanged). `raw_files/` must be non-empty for any run.
- Retrieval queries **both** indices, merges results by score, then dedups.

---

## 4. Storage and data contracts

### 4.1 Memgraph schema

Nodes (label = type), all carrying `session_id` and `source` properties:

| Label | Key properties |
|-------|----------------|
| `Material` | name, formula |
| `Property` | name, unit, value |
| `Parameter` | name, unit, value |
| `Process` | name, conditions |
| `Source` | doc_id, path, title, author, date |

Edges (relationship type), all carrying `provenance` (source_id, conditions):

| Rel type | From → To | Meaning |
|----------|-----------|---------|
| `influences` | Material/Parameter → Property | affects a property |
| `measured_as` | Property → Source | reported in a source |
| `composed_of` | Material → Material | composition |
| `contradicts` | Source → Source | conflicting reports (FE7) |

**Scoping**: every Cypher query filters `WHERE n.session_id IN [$sid, 'kb']` so
the global KB sub-graph and the session sub-graph are both visible to a run, but
sessions never leak into each other.

**Persistence**: Memgraph is in-memory. On ETL completion, the session sub-graph
is dumped to `sessions/<id>/index/graph.json` (Cypher dump via `mgconsole` or the
Python client). On startup, the global KB graph is loaded from
`knowledge_base/.index/graph.json`.

### 4.2 FAISS indices

- Two `faiss.IndexFlatIP` (cosine — vectors L2-normalized) indices: one for kb,
  one per session.
- Chunk metadata stored alongside in `chunks.json`: `{chunk_id, doc_id, page,
  text, meta:{source,date,author,conditions}}`.
- `chunk_id` is the join key between FAISS results, citation bind, and KG
  `Source` nodes.

### 4.3 sqlite session store

One `sessions/<id>/session.db` with tables:

| Table | Columns |
|-------|---------|
| `stage_state` | run_id, stage, status, started_at, ended_at, error |
| `artifacts` | run_id, stage, name, value_json |
| `traces` | run_id, stage, slot, token_in, token_out, latency_ms, status |
| `evals` | run_id, metric, value |

### 4.4 Configuration (`config.py`)

Extends the existing `AppConfig` with MVP knobs:

```python
@dataclass
class MVPConfig:
    # LLM
    provider: ProviderType
    model: str
    # Embeddings
    embeddings_model: str = "intfloat/multilingual-e5-small"
    embeddings_dim: int = 384
    # Retrieval
    vector_top_k: int = 20
    rerank_top_k: int = 8
    kg_hops: int = 2
    # Context budget
    context_budget_tokens: int = 16000
    # Timeouts (s)
    timeout_vector: int = 4
    timeout_kg: int = 3
    timeout_rerank: int = 8
    timeout_generate: int = 15
    timeout_export: int = 30
    # Gates
    citation_coverage_min: float = 0.5  # spec is 0.85; MVP relaxes, configurable
    # Retry caps
    fe1_max_query_expansion: int = 2
    fe2_max_reprompt: int = 3
    fe6_max_cite_regenerate: int = 2
    # Scorer weights (R-A1)
    weight_novelty: float = 0.3
    weight_feasibility: float = 0.4
    weight_effect: float = 0.3
    # Memgraph
    memgraph_uri: str = "bolt://localhost:7687"
```

---

## 5. End-to-end flow (run pipeline)

```
CLI: hfabric run <session_id> "reach +5% Au recovery, no cyanide increase"
  │
  ▼
1. KPI/Task Parser [LLM slot, structured]
   ├── input : raw NL query string
   └── output : {goal, kpi:{metric,direction,target}, constraints:[str], language}
2. Stage Router init run
3. Retrieve [det + LLM]
   ├── Query Planner : deterministic plan from kpi+constraints (keyword extraction)
   ├── Vector Search : query kb + session FAISS, vector_top_k each, merge, dedup
   ├── KG Traversal : Memgraph BFS kg_hops from matched entities (session_id-scoped)
   ├── LLM Rerank slot : rerank evidence under goal, keep rerank_top_k
   └── Context Budget Enforcer : truncate evidence to context_budget_tokens
       (FE1: evidence insufficient → expand query, cap fe1_max_query_expansion)
4. Generate [LLM slot, structured]
   ├── Candidate Synthesizer : LLM with tool-calling / JSON schema
   ├── schema : {claim, mechanism, expected_effect, evidence_refs:[chunk_id]}
   └── validate; (FE2: invalid → re-prompt cap fe2_max_reprompt)
5. Citation Bind [det]
   ├── fuzzy match claim text → chunk_id; compute coverage = matched/total
   └── gate cite coverage >= citation_coverage_min
       (FE6: below gate → re-generate demanding source, cap fe6_max_cite_regenerate)
6. Score [det only — FE3 path]
   ├── Feature Extractor:
   │     novelty         = graph distance (BFS hops) in Memgraph
   │     feasibility     = constraint-match (keyword/regex score)
   │     effect          = KPI-keyword proximity to kpi.metric/target
   ├── Weighted Ranker: score = Σ w_i * normalize(f_i)
   └── sort hypotheses; fixed weights from config
7. Constraint check [det, hard gate]
   ├── rule match against constraints[] (keyword/regex)
   └── (FE4: violation → drop hypothesis, log, loop back to Generate if any remain)
8. Explain [LLM slot]
   ├── Build per-hypothesis: claim → evidence → mechanism → uncertainty → verification_plan
   └── textual "graph": ASCII/neighbourhood dump from Memgraph
9. Export [det]
   └── write sessions/<id>/export/{report.md, hypotheses.json}
10. End: print ranked list to stdout, path to export files
```

### 5.1 Failure modes implemented

| ID | Trigger | MVP fallback |
|----|---------|-------------|
| FE1 | evidence insufficient after retrieve | expand query (relax filters), cap 2 → proceed with low-confidence flag |
| FE1b | retrieve empty | low-conf + log recommendation to add docs to raw_files/ |
| FE2 | candidates invalid (schema) | re-prompt slot, cap 3 → abort with `incomplete` |
| FE3 | LLM Judge (not implemented in MVP) | always det-only scorer — this *is* the MVP path |
| FE4 | constraint violation | drop hypothesis, log; if all dropped → end `incomplete` |
| FE5 | stage timeout | partial result + status `incomplete` |
| FE6 | citation coverage < gate | re-generate with explicit "must cite source" instruction, cap 2 |
| FE9 | ETL job failed | retry + dead-letter; keep last good index |

Stubs (not wired for MVP demo, interface only): FE7 (source conflict), FE8
(external API down).

---

## 6. Module specifications (MVP)

### M1 — Ingestion & ETL (per-session + global)

| Aspect | MVP choice |
|--------|-----------|
| Parser | `PyMuPDF` (fitz) for PDF; `python-docx` optional |
| Chunker | recursive text splitter, ~512 tokens, 64 overlap |
| Embeddings | `intfloat/multilingual-e5-small` via `sentence-transformers`; `query:`/`passage:` prefixes |
| Vector store | FAISS `IndexFlatIP` (L2-normalized cosine) |
| Entity extraction | regex (Material/Property/Process/Parameter) + **LLM-assisted normalisation** (a slot) |
| Graph build | insert nodes/edges into Memgraph with `session_id`/`source` |
| Idempotency | skip ETL if `index/faiss.bin` exists and `raw_files/` unchanged |
| Failure | FE9: retry + dead-letter |

CLI: `hfabric index-kb` (global), per-session ETL runs automatically inside
`hfabric new` / first `hfabric run`.

### M2 — Retriever

| Step | Type | Notes |
|------|------|-------|
| Query Planner | det | extract keywords from `goal`/`constraints`; build `query:` string for vector search |
| Vector Search | det | query kb + session FAISS, `vector_top_k` each |
| KG Traversal | det | Memgraph BFS `kg_hops` from entities matched in vector hits, `session_id`-scoped |
| LLM Reranker | LLM slot | rerank merged evidence under goal; keep `rerank_top_k` |
| Budget Enforcer | det | truncate list to `context_budget_tokens` (tiktoken count) |
| FE1 | det | if total tokens < threshold → expand query (relax KPI filters), cap 2 |
| FE1b | det | empty → low-confidence flag |

### M3 — Knowledge Graph Service

- Memgraph; schema as in §4.1.
- `kg_traverse(cypher: str, params: dict)` — **parameterised** Cypher (no string
  interpolation) to prevent injection.
- Helpers: `get_entities(name)`, `neighbours(node_id, hops)`,
`conflicts(source_id)`.
- A `source="kb"`/`source="session", session_id=<id>` split lets the session
  traverse both sub-graphs.

### M4 — Orchestrator (state machine)

- Implemented as a LangGraph `StateGraph` (consistent with existing `app.py` /
  `demo.py` patterns).
- State (`TypedDict`): `run_id, session_id, nl_query, kpi_parsed, evidence,
  candidates, cited, ranked, explained, export_path, status, traces`.
- Nodes: `kpi_parse`, `retrieve`, `generate`, `cite_bind`, `score`,
  `constraint_check`, `explain`, `export`.
- Transition rules: linear except FE1/FE2/FE4/FE6 loops with caps.
- Context Budget Enforcer is part of orchestration: wraps each LLM slot call.
- No canvas re-run (cut).

### M5 — Hypothesis Generator (one slot)

- Candidate Synthesizer using `llm.with_structured_output(Hypothesis)` (Pydantic
  schema), mirroring `demo.py`'s `with_structured_output` usage.
- Schema:
  ```python
  class Hypothesis(BaseModel):
      claim: str
      mechanism: str
      expected_effect: str
      evidence_refs: list[str]  # chunk_ids
  ```
- Validation: pydantic + non-empty `evidence_refs`; FE2 re-prompt cap 3.
- Language: output in `kpi_parsed.language`.
- Gap Finder (#10) cut.

### M6 — Scorer/Ranker (det only)

- Feature Extractor:
  - `novelty` = inverse of average Memgraph BFS distance from hypothesis entities
    to known entities (closer = less novel); normalized.
  - `feasibility` = `constraint_match_score(hypothesis, constraints)`.
  - `effect` = token/keyword overlap of `expected_effect` with `kpi.metric`/`target`.
- Weighted Ranker: `score = w_novelty*novelty + w_feasibility*feasibility
  + w_effect*effect` with weights from config. Normalize features to [0,1].
- LLM Judge is *not* wired (this is the FE3 det-only path used everywhere).
- Output: `ranked: list[(Hypothesis, score, features)]`.

### M7 — Justification & Explanation

- **Citation Bind (det)**: for each `evidence_refs[i]` (chunk_id), verify the
  chunk exists and that the claim is textually supported by a fuzzy
  (`rapidfuzz`) substring match above a threshold. Coverage = matched / total
  refs. Gate vs `citation_coverage_min`.
- **Explain (LLM slot)**: build `claim → evidence → mechanism → uncertainty →
  verification_plan`; emit a textual neighbourhood of the hypothesis's KG nodes
  (ASCII/indented list; no D3 render).
- FE6: below gate → re-generate with "you MUST cite an existing chunk from the
  list", cap 2.

### M8 — Memory & Context

- sqlite `session.db` (schema §4.3).
- Artifacts written after each stage (enables future canvas re-run).
- Context budget enforced in the Enforcer wrapper.
- Feedback Labels Store **cut** (no M10).

### M9 — Export & Integration

- Writer produces:
  - `hypotheses.json` — ranked list with all fields (claim, mechanism,
    expected_effect, evidence_refs with chunk text, score, features,
    justification, uncertainty, verification_plan).
  - `report.md` — human-readable Markdown: title, query, KPI summary, ranked
    hypotheses with evidence quotes, graph neighbourhood.
- Jira/YouTrack, roadmap **cut**.

### M11 — Serving & Config

- CLI (no FastAPI for MVP):
  - `hfabric index-kb` — build/refresh global KB index.
  - `hfabric new "<NL query>"` — create session, copy selected docs to
    `raw_files/`, build session index, persist `meta.json`.
  - `hfabric run <session_id> "<NL query>"` — execute the run pipeline; print
    ranked hypotheses + export paths.
- Config via `.env` + `config.py` dataclass; no RBAC, no on-prem runtime
  isolation (relaxed for MVP).

### M12 — Observability & Evals

- Python `logging` per stage; traces table in sqlite (token_in/out, latency).
- **Evals**:
  - 1–2 **golden hypotheses** authored by hand on the metallurgy corpus.
  - **Jaccard@10 re-run** sanity: run the same query twice with the same weights
    and verify `Jaccard@10 ≥ 0.9` (R-N1 reproducibility check).
  - schema-validity, citation-existence, constraint-pass checks wired into the
    scorer export.
- OTel cut.

---

## 7. LLM slots

The MVP reuses the existing `llm.py` (`create_chat_model`) which returns a
`langchain_openai.ChatOpenAI`-compatible model. Four LLM slots are used:

| Slot | Stage | Mode | Schema |
|------|-------|------|--------|
| KPI Parser | 1 | `with_structured_output` | `KPIParsed` |
| Reranker | 3 | plain completion (prompt + ranked list) | parsed JSON list |
| Synthesizer | 4 | `with_structured_output` | `Hypothesis[]` |
| Explain | 8 | plain completion | text + structured fields |

All slots receive **budget-truncated** context from the Enforcer.

---

## 8. Reproducibility guarantees

- Deterministic carcade: KPI parser result, query plan, vector search order
  (FAISS deterministic for `IndexFlatIP` ties broken by id), KG BFS, citation
  bind, feature extraction, weighted ranker — all without LLM.
- LLM influence is concentrated in slots whose **output is structurally
  validated** (KPI parse, generate) or discarded for ranking (rerank only
  reorders; if rerank fails, FE3-style fallback to vector-order).
- Fixed weights; no calibration.
- Two runs of the same query on the same indices → Jaccard@10 ≥ 0.9 (the only
  nondeterminism is LLM generation, but rerank+generate still produce near-identical
  ranked sets because evidence and constraints are deterministic).

---

## 9. Dependencies

```
langchain-openai, langgraph, pydantic
pymupdf                  # PDF parsing
sentence-transformers    # local embeddings (intfloat/multilingual-e5-small)
faiss-cpu                # vector index
neo4j (Python driver)    # also works with Memgraph via bolt
gqlalchemy               # Memgraph Python client (or use neo4j driver)
rapidfuzz                # citation bind fuzzy match
tiktoken                 # token counting for budget
python-dotenv
```

`docker-compose.yml` runs Memgraph (community image, Apache-2.0).

---

## 10. Demo scenario

```bash
# one-time
cp .env_example .env  # fill YC_* / ROUTERAI_API_KEY
docker compose up -d memgraph
hfabric index-kb      # builds knowledge_base/.index from the 5 metallurgy PDFs

# per run
hfabric new "increase Au flotation recovery by 5% without raising cyanide use"
# → creates sessions/<id>/, expects user to place docs in raw_files/
# (for demo, copy 1-2 KB PDFs into raw_files/, then:)
hfabric run <session_id> "increase Au flotation recovery by 5% without raising cyanide use"
# → prints ranked hypotheses, writes sessions/<id>/export/{report.md, hypotheses.json}
```

Expected output: 5–10 ranked hypotheses, each with a claim, mechanism, expected
effect, evidence quotes from the indexed PDFs, a score, and an uncertainty level.