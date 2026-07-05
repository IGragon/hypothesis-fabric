from __future__ import annotations

import os
import time
from datetime import datetime

import httpx
import streamlit as st

API_BASE = os.environ.get("HFABRIC_API", "http://localhost:8000")

_SUPPORTED_EXTS = ("pdf", "xlsx", "docx", "png", "jpg", "jpeg")
_RUN_STAGE_LABELS = {
    "indexing": "Индексация файлов (OCR, эмбеддинги)",
    "kpi_parse": "KPI-разбор",
    "retrieve": "Поиск основований",
    "generate": "Генерация гипотез",
    "cite_bind": "Привязка цитат",
    "score": "Оценка и ранжирование",
    "constraint_check": "Проверка ограничений",
    "explain": "Обоснование",
    "export": "Экспорт",
}
_PIPELINE_STAGES = [
    "kpi_parse", "retrieve", "generate", "cite_bind",
    "score", "constraint_check", "explain", "export",
]

st.set_page_config(
    page_title="Фабрика гипотез — v3",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
)

_GREEN_THEME_CSS = """
<style>
:root {
    --hf-bg: #060b0a;
    --hf-panel: #0e1a16;
    --hf-line: rgba(120, 200, 170, 0.2);
    --hf-text: #eafff4;
    --hf-muted: #8fb8a6;
    --hf-cyan: #34e2b0;
    --hf-mint: #48f5a6;
    --hf-amber: #ffc857;
    --hf-coral: #ff6b6b;
}
.stApp {
    background:
        radial-gradient(circle at 30% -20%, rgba(72, 245, 166, 0.10), transparent 38%),
        linear-gradient(135deg, #050a08 0%, #081210 44%, #0a1612 100%);
    color: var(--hf-text);
}
section[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #0a1410 0%, #0c1814 100%);
    border-right: 1px solid var(--hf-line);
}
.stMarkdown h1, .stMarkdown h2, .stMarkdown h3, .stMarkdown h4 { color: var(--hf-text); }
.stMarkdown h1 { font-weight: 800; letter-spacing: -0.01em; }
.stMarkdown h2 {
    color: var(--hf-mint);
    border-bottom: 1px solid var(--hf-line);
    padding-bottom: 6px;
    margin-top: 8px;
}
.stMarkdown h3 { color: var(--hf-cyan); font-size: 1.05rem; }
.stExpander { background: rgba(14, 26, 22, 0.55); border: 1px solid var(--hf-line); border-radius: 12px; }
.stExpander > details > summary { color: var(--hf-cyan); font-weight: 600; }
.stExpander > details > summary:hover { color: var(--hf-mint); }
.stButton > button {
    background: rgba(72, 245, 166, 0.08);
    border: 1px solid rgba(72, 245, 166, 0.30);
    color: var(--hf-text);
    border-radius: 10px;
    transition: all 0.16s ease;
}
.stButton > button:hover {
    background: rgba(72, 245, 166, 0.16);
    border-color: var(--hf-mint);
    color: var(--hf-mint);
}
.stButton > button[kind="primary"], .stButton > button[data-testid*="primary"] {
    background: linear-gradient(135deg, var(--hf-cyan), var(--hf-mint));
    color: #061014;
    font-weight: 700;
    border: none;
}
.stTextInput > div > input, .stTextArea > div > textarea, .stNumberInput input {
    background: rgba(8, 18, 14, 0.7) !important;
    border: 1px solid var(--hf-line) !important;
    color: var(--hf-text) !important;
    border-radius: 8px;
}
.stSlider > div > div > div { background: var(--hf-line); }
.stSlider > div > div > div > div { background: var(--hf-mint); }
.stMetric { background: rgba(14, 26, 22, 0.5); border: 1px solid var(--hf-line); border-radius: 10px; padding: 8px 12px; }
.stAlert { border-radius: 10px; }
.hf-feat-row {
    display: flex; align-items: center; gap: 8px;
    margin-bottom: 5px; padding: 2px 0;
}
.hf-feat-label {
    flex: 0 0 110px; color: var(--hf-text);
    font-size: 0.78rem; font-weight: 500;
}
.hf-feat-track {
    flex: 1; height: 8px; border-radius: 4px;
    background: rgba(120, 200, 170, 0.14);
    overflow: hidden;
}
.hf-feat-fill {
    height: 100%; border-radius: 4px;
    background: linear-gradient(90deg, var(--hf-cyan), var(--hf-mint));
    transition: width 0.3s ease;
}
.hf-feat-val {
    flex: 0 0 34px; text-align: right;
    color: var(--hf-muted); font-size: 0.76rem;
    font-weight: 700;
}
.hf-section-label {
    font-weight: 700; color: var(--hf-cyan);
    font-size: 0.92rem; margin-top: 8px; margin-bottom: 2px;
}
.hf-section-body {
    color: var(--hf-text); font-size: 0.88rem;
    line-height: 1.5; margin-bottom: 4px;
}
.hf-export-row {
    display: flex; align-items: center; gap: 10px;
    padding: 4px 0;
}
.hf-session-row {
    padding: 8px 10px; margin-bottom: 6px; border-radius: 10px;
    border: 1px solid var(--hf-line); background: rgba(14, 26, 22, 0.4);
    cursor: pointer; transition: all 0.14s;
}
.hf-session-row:hover { border-color: var(--hf-mint); background: rgba(72, 245, 166, 0.06); }
.hf-session-row.active { border-color: var(--hf-mint); background: rgba(72, 245, 166, 0.12); }
.hf-session-name { font-weight: 600; color: var(--hf-text); margin-bottom: 2px; font-size: 0.92rem; }
.hf-session-meta { color: var(--hf-muted); font-size: 0.76rem; }
.hf-chip {
    display: inline-block; padding: 2px 9px; border-radius: 999px;
    background: rgba(72, 245, 166, 0.14); color: var(--hf-cyan);
    font-size: 0.7rem; font-weight: 600; margin-left: 6px;
}
.hf-chip.amber { background: rgba(255, 200, 87, 0.14); color: var(--hf-amber); }
.hf-header {
    display: flex; align-items: center; gap: 12px;
    margin-bottom: 4px;
}
.hf-header .hf-mark {
    width: 38px; height: 38px; border-radius: 11px;
    background: linear-gradient(135deg, var(--hf-cyan), var(--hf-mint));
    color: #061014; display: grid; place-items: center;
    font-weight: 900; font-size: 1.05rem;
}
.hf-source-row {
    padding: 5px 0; border-bottom: 1px dashed var(--hf-line);
}
.hf-source-row:last-child { border-bottom: none; }
</style>
"""
st.markdown(_GREEN_THEME_CSS, unsafe_allow_html=True)


def _init_state() -> None:
    defaults = {
        "active_session": None,
        "last_run_id": None,
        "last_results": None,
        "last_session_loaded": None,
        "poll_until": 0.0,
        "toast": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


_init_state()


def api(method: str, path: str, **kwargs):
    url = f"{API_BASE}{path}"
    try:
        with httpx.Client(timeout=600.0) as client:
            r = client.request(method, url, **kwargs)
            if r.status_code >= 400:
                return None, f"API {method} {path} → {r.status_code}: {r.text[:200]}"
            return r.json(), None
    except Exception as e:
        return None, f"API error: {e}"


def api_download(path: str, params=None):
    url = f"{API_BASE}{path}"
    try:
        with httpx.Client(timeout=120.0) as client:
            r = client.get(url, params=params)
            if r.status_code >= 400:
                return None, f"Download {path} → {r.status_code}"
            return r.content, None
    except Exception as e:
        return None, f"Download error: {e}"


def _format_date(iso: str) -> str:
    if not iso:
        return "?"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
        return dt.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return iso[:19].replace("T", " ")


def _short_name(text: str, n: int = 64) -> str:
    text = (text or "").strip()
    if len(text) <= n:
        return text or "(без названия)"
    cut = text[:n].rsplit(" ", 1)[0]
    return cut + "…"


def _toast(msg: str) -> None:
    st.session_state.toast = msg


def _load_session_result(session_id: str) -> tuple[dict | None, str]:
    data, err = api("GET", f"/sessions/{session_id}/latest")
    return data, err


def _poll_stages(sid: str, rid: str) -> dict | None:
    data, err = api("GET", f"/sessions/{sid}/runs/{rid}/stages")
    if err or data is None:
        return None
    stages = {s["stage"]: s["status"] for s in data.get("stages", [])}
    return stages


def _render_sidebar() -> None:
    with st.sidebar:
        st.markdown(
            "<div class='hf-header'><div class='hf-mark'>ФГ</div>"
            "<div><strong style='font-size:1.1rem'>Фабрика гипотез</strong><br>"
            "<span style='color:var(--hf-muted);font-size:0.75rem'>v3 · сессионный режим</span></div></div>",
            unsafe_allow_html=True,
        )
        st.divider()

        with st.expander("➕ Новая сессия", expanded=st.session_state.active_session is None):
            problem = st.text_area(
                "Технологическая проблема / целевое свойство",
                placeholder="напр. повысить извлечение Au при флотации на 5% без увеличения расхода цианида",
                height=100,
                key="v3_problem",
            )
            constraints = st.text_area(
                "Ограничения (сырьё, бюджет, оборудование, нормативы)",
                placeholder="напр. доступное сырьё: ксантанат; бюджет ограничен; без CN",
                height=80,
                key="v3_constraints",
            )
            uploaded = st.file_uploader(
                "Файлы базы знаний",
                type=list(_SUPPORTED_EXTS),
                accept_multiple_files=True,
                key="v3_files",
                help="Поддерживаются: PDF, DOCX, XLSX, PNG, JPEG (другие форматы не принимаются)",
            )
            file_count = len(uploaded) if uploaded else 0
            st.caption(f"📎 Загружено файлов: **{file_count}**")

            st.caption("🌐 Внешние источники данных:")
            use_web = st.checkbox("Веб-поиск (DuckDuckGo)", value=True, key="v3_web")
            use_mp = st.checkbox("Materials Project", value=True, key="v3_mp")

            with st.expander("⚙️ Веса ранжирования"):
                c1, c2 = st.columns(2)
                with c1:
                    w_nov = st.slider("Новизна", 0.0, 1.0, 0.25, 0.05, key="v3_wn")
                    w_eff = st.slider("Эффект", 0.0, 1.0, 0.25, 0.05, key="v3_we")
                    w_risk = st.slider("Риски", 0.0, 1.0, 0.10, 0.05, key="v3_wr")
                with c2:
                    w_feas = st.slider("Реализуемость", 0.0, 1.0, 0.30, 0.05, key="v3_wf")
                    w_real = st.slider("Осуществимость", 0.0, 1.0, 0.10, 0.05, key="v3_wrl")

            examples, _ = api("GET", "/examples")
            ex_names = ["—"]
            if examples and examples.get("examples"):
                ex_names += [e["name"] for e in examples["examples"]]
            ex_sel = st.selectbox("Примеры (заполнить)", ex_names, key="v3_ex_sel")

            run_btn = st.button(
                "▶ Запустить анализ",
                type="primary",
                use_container_width=True,
                disabled=not problem.strip(),
                key="v3_run_btn",
            )

            if run_btn and problem.strip():
                _run_pipeline(problem, constraints, uploaded, use_web, use_mp,
                              w_nov, w_feas, w_eff, w_risk, w_real, ex_sel, examples)

        st.divider()
        st.markdown(f"###### 📁 Сессии")

        sessions_resp, _ = api("GET", "/sessions")
        sessions = (sessions_resp or {}).get("sessions", [])

        if not sessions:
            st.caption("Пока нет сессий. Создайте новую выше.")
        else:
            for s in sessions:
                sid = s.get("session_id", "")
                active = st.session_state.active_session == sid
                cls = "hf-session-row active" if active else "hf-session-row"
                name = _short_name(s.get("nl_query") or s.get("problem") or "(без названия)")
                meta = _format_date(s.get("created_at", ""))
                n_runs = len((s.get("runs") or []))
                chip = f'<span class="hf-chip">{n_runs} runs</span>' if n_runs else ""
                st.markdown(
                    f"<div class='{cls}'><div class='hf-session-name'>{name}</div>"
                    f"<div class='hf-session-meta'>создана {meta}{chip}</div></div>",
                    unsafe_allow_html=True,
                )
                if st.button("Открыть", key=f"open_{sid}", use_container_width=True):
                    st.session_state.active_session = sid
                    st.session_state.last_results = None
                    st.session_state.last_session_loaded = None
                    st.rerun()

        st.divider()
        st.caption("API: " + API_BASE)


def _run_pipeline(problem, constraints, uploaded, use_web, use_mp,
                  w_nov, w_feas, w_eff, w_risk, w_real, ex_sel, examples):
    sources = []
    if use_web:
        sources.append("web")
    if use_mp:
        sources.append("mp")
    ext_mode = ",".join(sources) if sources else "none"
    config_payload = {
        "weight_novelty": w_nov, "weight_feasibility": w_feas,
        "weight_effect": w_eff, "weight_risk": w_risk, "weight_realizability": w_real,
        "external_search": ext_mode,
    }
    with st.status("Запуск пайплайна…", expanded=True) as status:
        resp, err = api("POST", "/sessions", json={"problem": problem, "constraints": constraints})
        if err:
            st.error(err)
            status.update(label="Ошибка", state="error")
            st.stop()
        sid = resp["session_id"]
        st.session_state.active_session = sid
        st.write(f"Сессия: `{sid}`")

        if uploaded:
            files = [("files", (f.name, f.getvalue(), "application/octet-stream")) for f in uploaded]
            up, err = api("POST", f"/sessions/{sid}/upload", files=files)
            if up:
                st.write(f"Загружено файлов: {up['count']}")
            elif err:
                st.warning(err)

        st.write("Запуск пайплайна (8 этапов)…")
        run_resp, err = api("POST", f"/sessions/{sid}/run", json={
            "problem": problem, "constraints": constraints, "config": config_payload,
        })
        if err:
            st.error(err)
            status.update(label="Ошибка пайплайна", state="error")
            st.stop()
        rid = run_resp["run_id"]
        st.session_state.last_run_id = rid
        st.write(f"Run ID: `{rid}` — статус: {run_resp['status']}")
        status.update(label="Пайплайн запущен", state="complete")

    st.session_state.poll_until = time.time() + 600
    for key in ("v3_problem", "v3_constraints", "v3_files"):
        st.session_state.pop(key, None)
    st.rerun()


def _render_progress(sid: str, rid: str) -> bool:
    """Return True if pipeline still running (need to keep polling)."""
    stages = _poll_stages(sid, rid)
    if stages is None:
        return False

    done_count = sum(1 for s in _PIPELINE_STAGES if stages.get(s) == "done")
    all_done = done_count == len(_PIPELINE_STAGES)
    has_error = any(stages.get(s) == "error" for s in _PIPELINE_STAGES)

    with st.status(f"Выполнение этапов ({done_count}/{len(_PIPELINE_STAGES)})…", expanded=True):
        for stage in _PIPELINE_STAGES:
            status = stages.get(stage, "pending")
            label = _RUN_STAGE_LABELS.get(stage, stage)
            icon = {"done": "✅", "running": "🔄", "error": "❌", "pending": "⏳"}.get(status, "⏳")
            st.write(f"{icon} {label}: {status}")

    if all_done or has_error:
        if all_done:
            st.success("Пайплайн завершён ✓")
        else:
            st.error("Пайплайн завершился с ошибкой")
        return False
    return True


def _section(label: str, body: str) -> None:
    """Render a hypothesis section with a bold low-level header and body below.

    The label is rendered as a bold cyan header; the body is rendered as
    plain markdown (so [text](url) links are clickable).  We cannot wrap
    the body in a raw HTML <div> because Streamlit does not process markdown
    inside unsafe_allow_html HTML blocks.
    """
    st.markdown(f"**🟢 {label}**")
    if body:
        st.markdown(body)
    st.markdown("")


def _section_label(label: str) -> None:
    st.markdown(f"**🟢 {label}**")
    st.markdown("")


def _file_url(session_id: str, path: str) -> str:
    """Build a downloadable HTTP URL for a session raw file."""
    import urllib.parse
    filename = os.path.basename(path)
    return f"{API_BASE}/sessions/{session_id}/files/{urllib.parse.quote(filename)}"


def _linkify_text(text: str, refs: dict, session_id: str = "") -> str:
    """Convert [chunk_xxxx] / [web:xxxx] references into clickable markdown links.

    For web sources → the URL.  For local chunks → an HTTP download link
    served by the API (browsers block file:// for security).
    """
    import re as _re

    if not text or not refs:
        return text or ""

    def repl(m):
        marker = m.group(1).strip()
        chunk = refs.get(marker)
        if chunk is None:
            for c in refs.values():
                if (c.get("meta") or {}).get("url") == marker:
                    return f"[{marker}]({marker})"
            return f"[{marker}]"
        meta = chunk.get("meta") or {}
        url = meta.get("url")
        if url:
            return f"[{marker}]({url})"
        path = meta.get("path", "")
        if path and session_id:
            return f"[{marker}]({_file_url(session_id, path)})"
        return f"[{marker}]"

    return _re.sub(r"\[([^\]\n]+)\]", repl, text)


def _render_hypothesis(idx: int, eh: dict, sid: str, rid: str) -> None:
    scored = eh.get("scored", {})
    hyp = scored.get("hypothesis", {})
    score = scored.get("score", 0.0)
    feats = scored.get("features", {})
    refs = scored.get("cited_refs", {})

    claim_text = hyp.get('claim', 'N/A')
    short_claim = claim_text if len(claim_text) <= 80 else claim_text[:80].rsplit(' ', 1)[0] + '…'
    title = f"#{idx}  ·  Score: {score:.3f}  —  {short_claim}"
    with st.expander(title, expanded=(idx == 1)):
        st.markdown(f"**📝 Гипотеза:** {claim_text}")
        st.markdown("")
        m1, m2, m3 = st.columns([3, 3, 1])
        with m1:
            _section("Механизм", hyp.get('mechanism', 'N/A'))
            _section("Ожидаемый эффект", hyp.get('expected_effect', 'N/A'))
        with m2:
            _section("Признаки", "")
            for k, v in list(feats.items())[:8]:
                if isinstance(v, (int, float)):
                    pct = int(round(min(max(float(v), 0.0), 1.0) * 100))
                    st.markdown(
                        f"<div class='hf-feat-row'>"
                        f"<span class='hf-feat-label'>{k}</span>"
                        f"<div class='hf-feat-track'>"
                        f"<div class='hf-feat-fill' style='width:{pct}%'></div>"
                        f"</div>"
                        f"<span class='hf-feat-val'>{float(v):.2f}</span>"
                        f"</div>",
                        unsafe_allow_html=True,
                    )
        with m3:
            st.metric("Score", f"{score:.3f}")

        cv = eh.get("constraint_violations", [])
        if cv:
            st.warning(f"⚠ Предупреждения: {len(cv)} несоответствий ограничениям")
            for v in cv:
                st.markdown(f"- {v}")

        _section("Обоснование", _linkify_text(eh.get('justification', ''), refs, sid))
        _section("Новизна", _linkify_text(eh.get('novelty', ''), refs, sid))
        _section("Риски", _linkify_text(eh.get('risks', ''), refs, sid))
        _section("Почему важно (KPI / ценность)", _linkify_text(eh.get('why_it_matters', ''), refs, sid))

        exs = eh.get("effect_cause_examples", [])
        if exs:
            _section_label("Примеры эффект-причина")
            for ex in exs:
                st.markdown(f"- {_linkify_text(ex, refs, sid)}")

        _section("Общий подход", _linkify_text(eh.get('general_approach', ''), refs, sid))
        _section("Что сделать сейчас", _linkify_text(eh.get('actionable_now', ''), refs, sid))
        _section("Лучшие практики", _linkify_text(eh.get('best_practices', ''), refs, sid))
        _section("Неопределённость", _linkify_text(eh.get('uncertainty', ''), refs, sid))
        _section("План верификации", _linkify_text(eh.get('verification_plan', ''), refs, sid))

        _section_label("📚 Источники / цитаты")
        if refs:
            for cid, chunk in refs.items():
                _render_source(cid, chunk, sid)
        else:
            st.caption("Нет привязанных источников.")

        ext_urls = eh.get("external_urls", [])
        if ext_urls:
            _section_label("🌐 Внешние источники")
            for u in ext_urls:
                short = u if len(u) <= 70 else u[:67] + "…"
                st.markdown(f"- [{short}]({u})")

        nb = eh.get("graph_neighbourhood", [])
        if nb:
            with st.popover("Граф связей (текст)"):
                st.code("\n".join(nb))

        f1, f2, f3 = st.columns(3)
        claim = hyp.get("claim", "")
        with f1:
            if st.button("👍 Принять", key=f"acc_{idx}"):
                api("POST", f"/sessions/{sid}/runs/{rid}/feedback",
                    json={"claim": claim, "label": "accepted", "expert_id": "ui"})
                _toast("Сохранено: accepted")
                st.rerun()
        with f2:
            if st.button("👎 Отклонить", key=f"rej_{idx}"):
                api("POST", f"/sessions/{sid}/runs/{rid}/feedback",
                    json={"claim": claim, "label": "rejected", "expert_id": "ui"})
                _toast("Сохранено: rejected")
                st.rerun()
        with f3:
            if st.button("✎ Скорректировать", key=f"adj_{idx}"):
                api("POST", f"/sessions/{sid}/runs/{rid}/feedback",
                    json={"claim": claim, "label": "adjusted", "expert_id": "ui"})
                _toast("Сохранено: adjusted")
                st.rerun()


def _render_source(cid: str, chunk: dict, session_id: str = "") -> None:
    meta = chunk.get("meta") or {}
    text = chunk.get("text", "")
    url = meta.get("url")
    doc_id = meta.get("doc_id", chunk.get("doc_id", cid))
    page = meta.get("page", "")
    path = meta.get("path", "")
    location = f" · стр. {page}" if page else ""

    if url:
        title = meta.get("title") or url
        header_link = f"[{title}]({url})"
    elif path and session_id:
        header_link = f"[{doc_id}]({_file_url(session_id, path)})"
    else:
        header_link = doc_id

    header = f"`[{cid}]`  **{header_link}**{location}"
    with st.expander(header, expanded=False):
        st.caption(text)
        if path and not url:
            st.caption(f"📂 {path}")


def _render_export_bar(sid: str, rid: str) -> None:
    st.divider()
    st.markdown("#### Экспорт")
    formats = [
        ("md", "📄 Markdown (.md)", "report.md", "text/markdown"),
        ("json", "🗂 JSON", "hypotheses.json", "application/json"),
        ("docx", "📝 Word (.docx)", "report.docx",
         "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
        ("pdf", "📕 PDF (.pdf)", "report.pdf", "application/pdf"),
        ("csv", "📊 CSV (.csv)", "hypotheses.csv", "text/csv"),
    ]
    for fmt, label, fname, mime in formats:
        blob, err = api_download(f"/sessions/{sid}/runs/{rid}/export/download", params={"format": fmt})
        if blob and not err:
            st.download_button(label, data=blob, file_name=fname, mime=mime, key=f"dl_{fmt}",
                               use_container_width=True)
        else:
            st.button(label, disabled=True, key=f"dl_disabled_{fmt}",
                      use_container_width=True)

    st.markdown("")
    if st.button("📤 Экспорт в Jira", key="jira_btn", use_container_width=True):
        jr, err = api("POST", f"/sessions/{sid}/runs/{rid}/export/jira", json={})
        if jr and not err:
            if jr.get("exported") and jr["exported"][0].get("status") == "mocked":
                st.info("Jira не настроен — mock-ответ")
            st.success(f"Экспортировано задач: {jr.get('count', 0)}")
        elif err:
            st.error(err)

    if st.button("📤 Экспорт в YouTrack", key="yt_btn", use_container_width=True):
        yt, err = api("POST", f"/sessions/{sid}/runs/{rid}/export/youtrack", json={})
        if yt and not err:
            if yt.get("exported") and yt["exported"][0].get("status") == "mocked":
                st.info("YouTrack не настроен — mock-ответ")
            st.success(f"Экспортировано задач: {yt.get('count', 0)}")
        elif err:
            st.error(err)


def _render_main() -> None:
    if st.session_state.toast:
        st.toast(st.session_state.toast)
        st.session_state.toast = None

    sid = st.session_state.active_session

    if not sid:
        st.markdown(
            "<div style='text-align:center;padding-top:80px'>"
            "<h2>Добро пожаловать в Фабрику гипотез</h2>"
            "<p style='color:var(--hf-muted)'>Выберите или создайте сессию слева, "
            "запустите анализ и изучайте сгенерированные гипотезы.</p>"
            "</div>",
            unsafe_allow_html=True,
        )
        return

    sess, _ = api("GET", f"/sessions/{sid}")
    name = _short_name((sess or {}).get("nl_query") or "(без названия)")
    st.markdown(f"## 🧪 {name}")
    st.caption(f"Session ID: `{sid}` · создана { _format_date((sess or {}).get('created_at',''))}")

    rid = st.session_state.last_run_id
    results = st.session_state.last_results

    if rid and time.time() < st.session_state.poll_until:
        still_running = _render_progress(sid, rid)
        if still_running:
            time.sleep(3)
            st.rerun()
        else:
            st.session_state.poll_until = 0
            data, _ = _load_session_result(sid)
            if data:
                st.session_state.last_results = data
            st.rerun()
        return

    if results is None or st.session_state.last_session_loaded != sid:
        data, err = _load_session_result(sid)
        if data:
            st.session_state.last_results = data
            st.session_state.last_session_loaded = sid
            results = data
        elif err:
            st.info("В этой сессии ещё нет результатов. Запустите новый анализ через «Новая сессия» слева.")
            return

    if not results:
        st.info("В этой сессии ещё нет результатов.")
        return

    ranked = results.get("ranked", [])
    status = results.get("status", "")
    query = results.get("query", "")
    run_id = results.get("run_id", rid or "")

    st.caption(f"Статус: {status} · Гипотез: {len(ranked)}")
    if query:
        st.caption(f"Запрос: {query}")

    if not ranked:
        st.warning("Гипотезы не сгенерированы. Проверьте подключение к LLM и базу знаний.")
        return

    for i, eh in enumerate(ranked, 1):
        _render_hypothesis(i, eh, sid, run_id)

    _render_export_bar(sid, run_id)

    st.caption(
        "ℹ️ Оценки (принять/отклонить/скорректировать) калибруют веса ранжирования "
        "для следующих запусков в этой сессии (обучение на фидбэке — feedback loop)."
    )


_render_sidebar()
_render_main()