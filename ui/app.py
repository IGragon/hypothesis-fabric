from __future__ import annotations

import io
import os
import sys

import httpx
import streamlit as st

API_BASE = os.environ.get("HFABRIC_API", "http://localhost:8000")

st.set_page_config(page_title="Hypothesis Fabric", page_icon="🔬", layout="wide")

if "session_id" not in st.session_state:
    st.session_state.session_id = None
if "last_run_id" not in st.session_state:
    st.session_state.last_run_id = None
if "result" not in st.session_state:
    st.session_state.result = None


def api(method: str, path: str, **kwargs):
    url = f"{API_BASE}{path}"
    try:
        with httpx.Client(timeout=600.0) as client:
            r = client.request(method, url, **kwargs)
            if r.status_code >= 400:
                st.error(f"API {method} {path} → {r.status_code}: {r.text[:300]}")
                return None
            return r.json()
    except Exception as e:
        st.error(f"API error: {e}")
        return None


def api_download(path: str, params=None):
    url = f"{API_BASE}{path}"
    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.get(url, params=params)
            if r.status_code >= 400:
                st.error(f"Download {path} → {r.status_code}")
                return None
            return r.content
    except Exception as e:
        st.error(f"Download error: {e}")
        return None


st.title("Hypothesis Fabric — генератор гипотез")

with st.sidebar:
    st.header("Входные данные")
    problem = st.text_area(
        "Технологическая проблема / целевое свойство",
        placeholder="напр. повысить извлечение Au при флотации на 5% без увеличения расхода цианида",
        height=100,
    )
    constraints = st.text_area(
        "Ограничения (сырьё, бюджет, оборудование, нормативы)",
        placeholder="напр. доступное сырьё: ксантанат; бюджет ограничен; без CN",
        height=80,
    )
    uploaded = st.file_uploader(
        "База знаний (PDF / XLSX / PNG / DOCX)",
        type=["pdf", "xlsx", "docx", "png", "jpg", "jpeg", "bmp", "tiff", "webp"],
        accept_multiple_files=True,
    )

    st.divider()
    st.subheader("Настройки")
    st.caption("Внешние источники данных (grounding):")
    use_web = st.checkbox("Веб-поиск (DuckDuckGo)", value=True)
    use_mp = st.checkbox("Materials Project", value=False)
    use_cit = st.checkbox("Citrination", value=False,
                          help="Требуется CITRINATION_API_KEY; иначе источник пропускается")
    use_nims = st.checkbox("NIMS MatNavi", value=False,
                           help="Открытая БД материалов; HTML-парсинг best-effort")
    col1, col2, col3 = st.columns(3)
    with col1:
        w_nov = st.slider("Новизна", 0.0, 1.0, 0.25, 0.05)
    with col2:
        w_feas = st.slider("Реализуемость", 0.0, 1.0, 0.30, 0.05)
    with col3:
        w_eff = st.slider("Эффект", 0.0, 1.0, 0.25, 0.05)
    col4, col5 = st.columns(2)
    with col4:
        w_risk = st.slider("Риски", 0.0, 1.0, 0.10, 0.05)
    with col5:
        w_real = st.slider("Осуществимость", 0.0, 1.0, 0.10, 0.05)

    st.divider()
    examples = api("GET", "/examples") or {"examples": []}
    if examples["examples"]:
        ex_names = ["—"] + [e["name"] for e in examples["examples"]]
        ex_sel = st.selectbox("Примеры (заполнить)", ex_names)
        if ex_sel != "—" and st.button("Загрузить пример"):
            ex = next(e for e in examples["examples"] if e["name"] == ex_sel)
            st.session_state.ex_problem = ex.get("problem", "")
            st.session_state.ex_constraints = ex.get("constraints", "")
            st.session_state.ex_output = ex.get("output_text", "")
            st.session_state.ex_output_file = ex.get("output_file", "")
            st.rerun()

    st.divider()
    run_btn = st.button("▶ Запустить", type="primary", use_container_width=True,
                        disabled=not problem.strip())

if "ex_problem" in st.session_state and not problem:
    problem = st.session_state.pop("ex_problem")
    constraints = st.session_state.pop("ex_constraints", "")
    ex_output = st.session_state.pop("ex_output", "")
    ex_output_file = st.session_state.pop("ex_output_file", "")
    if ex_output:
        st.session_state.show_example_output = (ex_output, ex_output_file)
    st.rerun()

if st.session_state.get("show_example_output"):
    ex_output, ex_output_file = st.session_state.show_example_output
    with st.expander(f"📋 Пример готового вывода эксперта — {ex_output_file}", expanded=True):
        st.markdown(ex_output)
    if st.button("✕ Скрыть пример вывода"):
        st.session_state.pop("show_example_output", None)
        st.rerun()

if run_btn:
    sources = []
    if use_web:
        sources.append("web")
    if use_mp:
        sources.append("mp")
    if use_cit:
        sources.append("citrination")
    if use_nims:
        sources.append("nims")
    ext_mode = "none" if not sources else ",".join(sources)
    config_payload = {
        "weight_novelty": w_nov, "weight_feasibility": w_feas,
        "weight_effect": w_eff, "weight_risk": w_risk, "weight_realizability": w_real,
        "external_search": ext_mode,
    }
    with st.status("Создание сессии…", expanded=True) as status:
        resp = api("POST", "/sessions", json={"problem": problem, "constraints": constraints})
        if resp is None:
            status.update(label="Ошибка", state="error")
            st.stop()
        sid = resp["session_id"]
        st.session_state.session_id = sid
        st.write(f"Сессия: `{sid}`")

        if uploaded:
            files = []
            for f in uploaded:
                files.append(("files", (f.name, f.getvalue(), "application/octet-stream")))
            up = api("POST", f"/sessions/{sid}/upload", files=files)
            if up:
                st.write(f"Загружено файлов: {up['count']} — {', '.join(up['saved'])}")

        st.write("Запуск пайплайна (KPI → retrieve → generate → cite → score → constraint → explain → export)…")
        run_resp = api("POST", f"/sessions/{sid}/run", json={
            "problem": problem, "constraints": constraints, "config": config_payload,
        })
        if run_resp is None:
            status.update(label="Ошибка пайплайна", state="error")
            st.stop()
        rid = run_resp["run_id"]
        st.session_state.last_run_id = rid
        st.write(f"Run ID: `{rid}` — статус: {run_resp['status']}")
        status.update(label="Пайплайн завершён", state="complete")

    result = api("GET", f"/sessions/{sid}/runs/{rid}")
    if result:
        st.session_state.result = result
    else:
        st.session_state.result = None
    st.rerun()

result = st.session_state.result
if result is None:
    st.info("Введите описание проблемы и ограничения слева, загрузите файлы базы знаний и нажмите **▶ Запустить**.")
    st.stop()

sid = st.session_state.session_id
rid = result.get("run_id", st.session_state.last_run_id)

st.subheader(f"Результаты — {len(result.get('ranked', []))} гипотез")
st.caption(f"Запрос: {result.get('query', '')}  ·  Статус: {result.get('status', '')}")

ranked = result.get("ranked", [])
if not ranked:
    st.warning("Гипотезы не сгенерированы. Проверьте подключение к LLM и базу знаний.")
    st.stop()

for i, eh in enumerate(ranked, 1):
    scored = eh.get("scored", {})
    hyp = scored.get("hypothesis", {})
    score = scored.get("score", 0.0)
    feats = scored.get("features", {})
    refs = scored.get("cited_refs", {})

    with st.expander(f"#{i}  Score: {score:.3f}  —  {hyp.get('claim', 'N/A')[:90]}", expanded=(i == 1)):
        mc1, mc2, mc3 = st.columns([2, 2, 1])
        with mc1:
            st.markdown(f"**Механизм:** {hyp.get('mechanism', 'N/A')}")
            st.markdown(f"**Ожидаемый эффект:** {hyp.get('expected_effect', 'N/A')}")
        with mc2:
            st.markdown("**Признаки:**")
            for k, v in feats.items():
                st.progress(min(max(v, 0.0), 1.0), text=f"{k}: {v:.2f}")
        with mc3:
            st.metric("Score", f"{score:.3f}")

        st.markdown(f"**Обоснование:** {eh.get('justification', 'N/A')}")
        st.markdown(f"**Новизна:** {eh.get('novelty', 'N/A')}")
        st.markdown(f"**Риски:** {eh.get('risks', 'N/A')}")
        st.markdown(f"**Почему это важно (KPI/ценность):** {eh.get('why_it_matters', 'N/A')}")

        exs = eh.get("effect_cause_examples", [])
        if exs:
            st.markdown("**Примеры эффект-причина:**")
            for ex in exs:
                st.markdown(f"- {ex}")

        st.markdown(f"**Как решается задача в общем:** {eh.get('general_approach', 'N/A')}")
        st.markdown(f"**Что можно сделать здесь и сейчас:** {eh.get('actionable_now', 'N/A')}")
        st.markdown(f"**Существующие лучшие практики:** {eh.get('best_practices', 'N/A')}")
        st.markdown(f"**Неопределённость:** {eh.get('uncertainty', 'N/A')}")
        st.markdown(f"**План верификации (roadmap):** {eh.get('verification_plan', 'N/A')}")

        if refs:
            st.markdown("**Источники / цитаты:**")
            for cid, chunk in refs.items():
                meta = chunk.get("meta", {})
                url = meta.get("url")
                if url:
                    title = meta.get("title") or url
                    st.markdown(f"- `[{cid}]` [{title}]({url})")
                else:
                    doc = meta.get("doc_id", chunk.get("doc_id", ""))
                    st.markdown(f"- `[{cid}]` *{doc}*: {chunk.get('text','')[:220]}")

        ext_urls = eh.get("external_urls", [])
        if ext_urls:
            st.markdown("**Внешние источники:**")
            for u in ext_urls:
                st.markdown(f"- {u}")

        nb = eh.get("graph_neighbourhood", [])
        if nb:
            with st.popover("Граф связей (текст)"):
                st.code("\n".join(nb))

        fb1, fb2, fb3 = st.columns(3)
        claim = hyp.get("claim", "")
        with fb1:
            if st.button("👍 Принять", key=f"acc_{i}"):
                api("POST", f"/sessions/{sid}/runs/{rid}/feedback",
                    json={"claim": claim, "label": "accepted", "expert_id": "ui"})
                st.toast("Сохранено: accepted")
        with fb2:
            if st.button("👎 Отклонить", key=f"rej_{i}"):
                api("POST", f"/sessions/{sid}/runs/{rid}/feedback",
                    json={"claim": claim, "label": "rejected", "expert_id": "ui"})
                st.toast("Сохранено: rejected")
        with fb3:
            if st.button("✎ Скорректировать", key=f"adj_{i}"):
                api("POST", f"/sessions/{sid}/runs/{rid}/feedback",
                    json={"claim": claim, "label": "adjusted", "expert_id": "ui"})
                st.toast("Сохранено: adjusted")

    st.caption(
    "ℹ️ Оценки сохраняются и калибруют веса ранжирования для следующих "
    "запусков в этой сессии (обучение на фидбэке — feedback loop)."
)

st.divider()
dc1, dc2, dc3, dc4, dc5 = st.columns(5)
with dc1:
    md_bytes = api_download(f"/sessions/{sid}/runs/{rid}/export/download", params={"format": "md"})
    if md_bytes:
        st.download_button("📄 .md", data=md_bytes, file_name="report.md", mime="text/markdown")
with dc2:
    json_bytes = api_download(f"/sessions/{sid}/runs/{rid}/export/download", params={"format": "json"})
    if json_bytes:
        st.download_button("🗂 .json", data=json_bytes, file_name="hypotheses.json", mime="application/json")
with dc3:
    docx_bytes = api_download(f"/sessions/{sid}/runs/{rid}/export/download", params={"format": "docx"})
    if docx_bytes:
        st.download_button("📝 .docx", data=docx_bytes, file_name="report.docx",
                           mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document")
with dc4:
    pdf_bytes = api_download(f"/sessions/{sid}/runs/{rid}/export/download", params={"format": "pdf"})
    if pdf_bytes:
        st.download_button("📕 .pdf", data=pdf_bytes, file_name="report.pdf", mime="application/pdf")
with dc5:
    csv_bytes = api_download(f"/sessions/{sid}/runs/{rid}/export/download", params={"format": "csv"})
    if csv_bytes:
        st.download_button("📊 .csv", data=csv_bytes, file_name="hypotheses.csv", mime="text/csv")

jc1, jc2, jc3 = st.columns(3)
with jc1:
    if st.button("📤 Экспорт в Jira"):
        jr = api("POST", f"/sessions/{sid}/runs/{rid}/export/jira", json={})
        if jr:
            if jr.get("count", 0) and jr["exported"][0].get("status") == "mocked":
                st.info("Jira не настроен (задайте JIRA_BASE_URL/JIRA_API_TOKEN) — возвращён mock-ответ.")
            st.success(f"Экспортировано задач: {jr.get('count', 0)}")
with jc2:
    if st.button("📤 Экспорт в YouTrack"):
        yt = api("POST", f"/sessions/{sid}/runs/{rid}/export/youtrack", json={})
        if yt:
            if yt.get("count", 0) and yt["exported"][0].get("status") == "mocked":
                st.info("YouTrack не настроен (задайте YOUTRACK_BASE_URL/YOUTRACK_TOKEN) — возвращён mock-ответ.")
            st.success(f"Экспортировано задач: {yt.get('count', 0)}")
with jc3:
    pass

with st.expander("Визуализация графа связей"):
    graph = api("GET", f"/sessions/{sid}/runs/{rid}/graph")
    if graph and graph.get("nodes"):
        try:
            from streamlit_agraph import agraph, Node, Edge, Config

            nodes = [Node(id=n["id"], label=n.get("name", n["id"])[:20],
                          size=25 if n["label"] == "Hypothesis" else 18,
                          group=n["label"]) for n in graph["nodes"]]
            edges = [Edge(source=e["source"], target=e["target"], label=e.get("rel", "")) for e in graph["edges"]]
            config = Config(width=800, height=500, directed=True, physics=True, nodeHighlightEffect=True,
                            highlightColor="#F7A7A6")
            agraph(nodes=nodes, edges=edges, config=config)
        except Exception as e:
            st.warning(f"agraph недоступен ({e}); показываю список рёбер")
            st.json(graph)
    else:
        st.caption("Граф пуст.")
