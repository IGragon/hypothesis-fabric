from __future__ import annotations

import os
import time
import uuid

os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")
os.environ.setdefault("STREAMLIT_WATCH_USE_LIBRARIES", "false")

import streamlit as st

from hfabric.config import MVPConfig, ProviderType
from hfabric.embeddings import SentenceTransformersProvider
from hfabric.etl import ETL
from hfabric.etl.faiss_index import index_exists
from hfabric.kg.schema import load_schema
from hfabric.retriever.budget import truncate_to_budget
from hfabric.retriever.kg_retrieval import retrieve_kg_evidence
from hfabric.retriever.query_plan import build_query_plan
from hfabric.retriever.rerank import rerank_evidence
from hfabric.retriever.vector import merge_results, query_faiss
from hfabric.schemas import EvidenceChunk, KPI, KPIParsed

KB_DIR = "knowledge_base"
KB_INDEX_DIR = "knowledge_base/.index/kb"
PLAYGROUND_DIR = "playground"
SESSIONS_DIR = os.path.join(PLAYGROUND_DIR, "sessions")

SUPPORTED_EXTS = (".pdf", ".xlsx", ".docx", ".png", ".jpg", ".jpeg", ".bmp", ".tiff", ".webp")

st.set_page_config(page_title="Hypothesis Fabric — Playground", page_icon="🔎", layout="wide")


def _load_env() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv()
    except Exception:
        pass


_load_env()


class _NoopKG:
    def add_entities(self, entities, session_id=None, source=""):
        pass

    def add_edges(self, edges, session_id=None, source=""):
        pass

    def traverse(self, cypher, params=None):
        return []

    def get_entities(self, name):
        return []

    def neighbours(self, node_id, hops=2):
        return []

    def conflicts(self, source_id):
        return []

    def dump(self, path):
        pass

    def load(self, path):
        pass


@st.cache_data(show_spinner=False)
def _kb_index_status() -> dict:
    if not index_exists(KB_INDEX_DIR):
        return {"exists": False, "num_chunks": 0}
    import json

    with open(os.path.join(KB_INDEX_DIR, "chunks.json")) as f:
        chunks = json.load(f)
    return {"exists": True, "num_chunks": len(chunks)}


def _get_embeddings(config: MVPConfig):
    if "embeddings" not in st.session_state:
        st.session_state.embeddings = SentenceTransformersProvider(config.embeddings_model)
    return st.session_state.embeddings


def _get_kg(config: MVPConfig):
    if "kg" in st.session_state:
        return st.session_state.kg
    try:
        from hfabric.kg.client import MemgraphKG

        kg_schema = load_schema(getattr(config, "kg_schema_path", None))
        kg = MemgraphKG(
            config.memgraph_uri,
            node_labels=kg_schema.node_labels,
            edge_types=kg_schema.edge_types,
        )
        st.session_state.kg_kind = "memgraph"
        st.session_state.kg = kg
        return kg
    except Exception as exc:
        st.session_state.kg_kind = "noop"
        st.session_state.kg_error = str(exc)[:200]
        st.session_state.kg = _NoopKG()
        return st.session_state.kg


def _try_build_llm(config: MVPConfig):
    if "llm" in st.session_state:
        return st.session_state.llm
    try:
        from hfabric.llm import create_chat_model

        llm = create_chat_model(config.provider, config.model, temperature=config.temperature)
        st.session_state.llm = llm
        return llm
    except Exception as exc:
        st.session_state.llm_error = str(exc)[:200]
        return None


def _index_label(built: bool) -> str:
    return "✅ built" if built else "❌ not built"


with st.sidebar:
    st.header("Playground settings")

    provider_opt = st.selectbox(
        "LLM provider (optional)",
        options=[p.value for p in ProviderType],
        index=list(ProviderType).index(ProviderType.LOCAL),
        help="If API keys are missing, the playground falls back to vector-only retrieval (no rerank).",
    )
    use_rerank = st.checkbox("Use LLM rerank", value=True)
    use_llm_kpi = st.checkbox("Use LLM to parse query into KPI", value=False)

    st.divider()
    st.subheader("Retrieval knobs")
    vector_top_k = st.slider("vector_top_k (per index)", 5, 50, 20, 1)
    rerank_top_k = st.slider("rerank_top_k (final)", 3, 30, 8, 1)
    kg_hops = st.slider("kg_hops", 1, 4, 2, 1)
    context_budget = st.slider("context_budget_tokens", 2000, 32000, 16000, 1000)

    st.divider()
    st.subheader("Workspace")
    st.caption(f"Session files: `{SESSIONS_DIR}/`")
    if st.button("🗑 Reset session", help="Drop uploaded docs and reinit session"):
        if "active_session_id" in st.session_state:
            sid = st.session_state.active_session_id
            sdir = os.path.join(SESSIONS_DIR, sid)
            if os.path.isdir(sdir):
                import shutil

                shutil.rmtree(sdir, ignore_errors=True)
        for k in ("embeddings", "llm", "kg", "active_session_id"):
            st.session_state.pop(k, None)
        st.rerun()

    st.divider()
    kg_kind = st.session_state.get("kg_kind")
    if kg_kind == "memgraph":
        st.caption("KG: Memgraph (live)")
    elif kg_kind == "noop":
        st.caption("KG: Memgraph not reachable — using no-op (KG enrichment disabled)")
        if st.session_state.get("kg_error"):
            st.caption(f"reason: {st.session_state.kg_error}")
    else:
        st.caption("KG: not initialized yet")

config = MVPConfig(provider=ProviderType(provider_opt))
config.vector_top_k = vector_top_k
config.rerank_top_k = rerank_top_k
config.kg_hops = kg_hops
config.context_budget_tokens = context_budget

embeddings = _get_embeddings(config)
kg = _get_kg(config)
llm = _try_build_llm(config)
llm_available = llm is not None
rerank_on = use_rerank and llm_available

st.title("Hypothesis Fabric — Retrieval Playground")
st.caption(
    "Load documents, build a FAISS index, and inspect retrieved evidence with its sources. "
    "No hypothesis synthesis is performed — this is a retrieval inspection surface for the "
    "Hypothesis Fabric pipeline."
)
if not llm_available:
    st.info(
        "LLM not configured (missing API keys). Retrieval runs in vector-only mode (no rerank). "
        "Set provider env vars (e.g. DEEPSEEK_API_KEY) and reset the session to enable rerank."
    )

st.divider()

left, right = st.columns([1, 2])

with left:
    kb_status = _kb_index_status()

    st.subheader("Knowledge base index")
    st.write(f"Status: {_index_label(kb_status['exists'])}")
    if kb_status["exists"]:
        st.caption(f"{kb_status['num_chunks']} chunks in `{KB_INDEX_DIR}`")
    build_kb_disabled = not os.path.isdir(KB_DIR)
    if build_kb_disabled:
        st.caption(f"`{KB_DIR}/` not found — place PDFs there to build the KB index.")
    if st.button("🔄 (Re)build KB index", disabled=build_kb_disabled):
        etl = ETL(embeddings, kg, config)
        with st.spinner("Building KB index from knowledge_base/ PDFs…"):
            try:
                artifact = etl.build_index(KB_DIR, KB_INDEX_DIR, "kb", "kb")
                st.success(f"KB index built: {artifact.num_chunks} chunks")
                _kb_index_status.clear()
                st.rerun()
            except Exception as exc:
                st.error(f"KB index build failed: {exc}")

    st.divider()

    st.subheader("Your documents")
    if "active_session_id" not in st.session_state:
        st.session_state.active_session_id = "playground_" + str(uuid.uuid4())[:8]

    session_id = st.session_state.active_session_id
    raw_dir = os.path.join(SESSIONS_DIR, session_id, "raw_files")
    index_dir = os.path.join(SESSIONS_DIR, session_id, "index")
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(index_dir, exist_ok=True)

    raw_files = sorted(
        f for f in os.listdir(raw_dir) if f.lower().endswith(SUPPORTED_EXTS)
    )

    uploaded = st.file_uploader(
        "Upload PDF / DOCX / XLSX / images",
        type=[e.lstrip(".") for e in SUPPORTED_EXTS],
        accept_multiple_files=True,
        key=f"uploader_{session_id}",
    )
    new_files: list[str] = []
    if uploaded:
        for f in uploaded:
            dest = os.path.join(raw_dir, f.name)
            existing_size = os.path.getsize(dest) if os.path.isfile(dest) else -1
            if existing_size != f.size:
                with open(dest, "wb") as out:
                    out.write(f.getbuffer())
                new_files.append(f.name)
        raw_files = sorted(
            f for f in os.listdir(raw_dir) if f.lower().endswith(SUPPORTED_EXTS)
        )
        st.success(
            f"Saved {len(uploaded)} file(s) to session raw_files/"
            + (f" ({len(new_files)} new)" if new_files else " — all already present")
        )

    st.caption(f"{len(raw_files)} file(s) in session raw_files/")
    if raw_files:
        with st.expander("Session files", expanded=False):
            for f in raw_files:
                st.code(f)

    session_built = index_exists(index_dir)

    def _build_session_index():
        etl = ETL(embeddings, kg, config)
        with st.spinner("Parsing + chunking + embedding your documents…"):
            try:
                artifact = etl.build_index(raw_dir, index_dir, session_id, "session")
                st.success(f"Session index built: {artifact.num_chunks} chunks")
                st.session_state.session_built_flag = True
            except Exception as exc:
                st.error(f"Session index build failed: {exc}")
                import traceback

                with st.expander("Traceback"):
                    st.code(traceback.format_exc())

    build_btn_label = "🔨 Build session index" if not session_built else "🔄 Rebuild session index"
    if st.button(build_btn_label, disabled=not raw_files):
        _build_session_index()
        st.rerun()

    st.caption(f"Session index: {_index_label(index_exists(index_dir))}")

    if not kb_status["exists"] and not index_exists(index_dir):
        st.warning(
            "No index available yet. Click **Build session index** above (or build the KB "
            "index) before querying."
        )

with right:
    st.subheader("Query")
    nl_query = st.text_area(
        "Natural-language query",
        placeholder="e.g. ways to increase Au flotation recovery without raising cyanide use",
        height=80,
    )

    can_llm_kpi = use_llm_kpi and llm_available
    use_manual_kpi = st.checkbox(
        "Provide KPI fields manually (else LLM parse or fallback to query text)",
        value=not can_llm_kpi,
    )
    metric = direction = target = constraints = language = ""
    if use_manual_kpi:
        c1, c2, c3 = st.columns(3)
        with c1:
            metric = st.text_input("metric", placeholder="Au recovery")
        with c2:
            direction = st.selectbox("direction", ["increase", "decrease", "maintain"])
        with c3:
            target = st.text_input("target", placeholder="+5%")
        constraints = st.text_input(
            "constraints (comma-separated)",
            placeholder="no cyanide increase, budget limited",
        )
        language = st.selectbox("language", ["ru", "en"], index=1)

    run_btn = st.button(
        "🔎 Retrieve evidence", type="primary", disabled=not nl_query.strip()
    )

if run_btn and nl_query.strip():
    if not kb_status["exists"] and not session_built:
        st.error("No index available — build KB or session index first.")
        st.stop()

    if can_llm_kpi:
        with st.status("Parsing query with LLM…", expanded=True) as status:
            try:
                structured = llm.with_structured_output(KPIParsed, method="function_calling")
                kpi = structured.invoke(nl_query)
                st.write(f"Parsed KPI: metric={kpi.kpi.metric}, direction={kpi.kpi.direction}, "
                         f"constraints={len(kpi.constraints)}")
                status.update(label="KPI parsed", state="complete")
            except Exception as exc:
                st.warning(f"LLM KPI parse failed ({exc}); falling back to query text.")
                kpi = KPIParsed(
                    goal=nl_query,
                    kpi=KPI(metric="unknown", direction="increase", target=None),
                    constraints=[],
                    language="en",
                )
    elif use_manual_kpi:
        kpi = KPIParsed(
            goal=nl_query,
            kpi=KPI(metric=metric or "unknown", direction=direction or "increase",
                    target=target or None),
            constraints=[c.strip() for c in constraints.split(",") if c.strip()],
            language=language or "en",
        )
    else:
        kpi = KPIParsed(
            goal=nl_query,
            kpi=KPI(metric="unknown", direction="increase", target=None),
            constraints=[],
            language="en",
        )

    with right:
        st.divider()
        st.subheader("Retrieval result")

        with st.status("Running retrieval…", expanded=True) as status:
            plan = build_query_plan(kpi)
            st.write("**Query plan**")
            st.code(
                f"query_text: {plan['query_text']}\n"
                f"keywords: {', '.join(plan['keywords'])}\n"
                f"kg_entities: {', '.join(plan['kg_entities'])}",
            )

            query_vector = embeddings.embed([plan["query_text"]], prefix="")[0]
            kb_results: list[EvidenceChunk] = []
            session_results: list[EvidenceChunk] = []
            if kb_status["exists"]:
                try:
                    kb_results = query_faiss(KB_INDEX_DIR, query_vector, config.vector_top_k)
                except Exception as exc:
                    st.warning(f"KB query failed: {exc}")
            if session_built:
                try:
                    session_results = query_faiss(index_dir, query_vector, config.vector_top_k)
                except Exception as exc:
                    st.warning(f"Session query failed: {exc}")

            merged = merge_results(kb_results, session_results)
            chunks_by_id = {c.chunk_id: c for c in merged}

            kg_chunks: list[EvidenceChunk] = []
            if st.session_state.get("kg_kind") == "memgraph":
                try:
                    kg_chunks = retrieve_kg_evidence(
                        kg, plan["kg_entities"], chunks_by_id, config.kg_hops
                    )
                    for c in kg_chunks:
                        chunks_by_id.setdefault(c.chunk_id, c)
                except Exception as exc:
                    st.warning(f"KG retrieval failed: {exc}")
            all_evidence = list(merged)
            for c in kg_chunks:
                if c.chunk_id not in {x.chunk_id for x in all_evidence}:
                    all_evidence.append(c)

            st.write(
                f"Vector hits — KB: {len(kb_results)}, session: {len(session_results)}, "
                f"merged (dedup): {len(merged)}, KG enrichment: {len(kg_chunks)}"
            )

            low_confidence = False
            if not all_evidence:
                st.warning("No evidence retrieved.")
                status.update(label="Done (empty)", state="complete")
                st.stop()

            if rerank_on:
                st.write(f"LLM rerank → top {config.rerank_top_k} …")
                try:
                    reranked, low_confidence = rerank_evidence(
                        all_evidence, kpi.goal, llm,
                        config.rerank_top_k, config.fe1_max_query_expansion,
                    )
                except Exception as exc:
                    st.warning(f"Rerank failed ({exc}); using vector order.")
                    reranked = all_evidence[: config.rerank_top_k]
            else:
                reranked = all_evidence[: config.rerank_top_k]

            truncated = truncate_to_budget(reranked, config.context_budget_tokens)
            elapsed = time.perf_counter() - 0
            st.write(
                f"Final evidence: {len(truncated)} chunks "
                f"(low_confidence={low_confidence})"
            )
            status.update(label="Retrieval complete", state="complete")

        st.session_state.last_results = {
            "kpi": kpi.model_dump(),
            "plan": plan,
            "evidence": [c.model_dump() for c in truncated],
            "all_vector": len(merged),
            "kg_chunks": len(kg_chunks),
            "low_confidence": low_confidence,
            "kb_hits": len(kb_results),
            "session_hits": len(session_results),
        }
        st.rerun()

results = st.session_state.get("last_results")
if not results:
    st.info(
        "Enter a query on the right and press **🔎 Retrieve evidence**. "
        "Build at least one index first (KB or session)."
    )
    st.stop()

kpi_dump = results["kpi"]
plan = results["plan"]
evidence = results["evidence"]

st.divider()
st.subheader("Parsed query")
with st.expander("KPI", expanded=False):
    st.json({
        "goal": kpi_dump["goal"],
        "kpi": kpi_dump["kpi"],
        "constraints": kpi_dump["constraints"],
        "language": kpi_dump["language"],
    })
with st.expander("Retrieval plan", expanded=False):
    st.code(
        f"query_text: {plan['query_text']}\n"
        f"keywords: {', '.join(plan['keywords'])}\n"
        f"kg_entities: {', '.join(plan['kg_entities'])}",
    )

st.subheader(f"Retrieved evidence — {len(evidence)} chunks")
m1, m2, m3, m4, m5 = st.columns(5)
with m1:
    st.metric("KB hits", results["kb_hits"])
with m2:
    st.metric("Session hits", results["session_hits"])
with m3:
    st.metric("Merged (dedup)", results["all_vector"])
with m4:
    st.metric("KG enrichment", results["kg_chunks"])
with m5:
    st.metric("Low confidence", "yes" if results["low_confidence"] else "no")

if not evidence:
    st.warning("No chunks returned.")
    st.stop()

sources: dict[str, list[dict]] = {}
for c in evidence:
    meta = c.get("meta", {})
    doc_id = c.get("doc_id") or meta.get("doc_id") or "(unknown)"
    sources.setdefault(doc_id, []).append(c)

st.subheader("Sources")
src_c1, src_c2 = st.columns([2, 3])
with src_c1:
    for doc_id, chunks in sorted(sources.items()):
        meta0 = chunks[0].get("meta", {})
        page = meta0.get("page", "—")
        path = meta0.get("path", meta0.get("doc_id", ""))
        section = meta0.get("section", "")
        label = f"{doc_id} ({len(chunks)} chunk(s))"
        with st.expander(label, expanded=False):
            st.caption(f"path: {path} · page: {page}" + (f" · section: {section}" if section else ""))
            for ch in chunks:
                st.code(ch.get("text", "")[:280])

with src_c2:
    st.markdown("**Per-chunk ranking**")
    for i, c in enumerate(evidence, 1):
        meta = c.get("meta", {})
        score = meta.get("score")
        score_str = f"{score:.3f}" if isinstance(score, (int, float)) else "—"
        doc_id = c.get("doc_id") or meta.get("doc_id") or "(unknown)"
        with st.expander(
            f"#{i}  score={score_str}  ·  {c.get('chunk_id', '')}  ·  {doc_id}",
            expanded=False,
        ):
            st.caption(
                f"chunk_id: {c.get('chunk_id', '')} · "
                f"doc: {doc_id} · "
                f"page: {meta.get('page', '—')} · "
                f"section: {meta.get('section', '—')}"
            )
            st.write(c.get("text", ""))

st.divider()
if st.button("Clear results"):
    st.session_state.pop("last_results", None)
    st.rerun()