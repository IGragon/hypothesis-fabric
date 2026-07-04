from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeout
from datetime import datetime, timezone
from typing import Any, Callable

from hfabric.schemas import EvidenceChunk, KPIParsed

_log = logging.getLogger("hfabric.external")

_WEB_BACKENDS = ["auto", "bing,duckduckgo", "brave,yandex", "google,wikipedia"]
_WEB_REGION = os.environ.get("HFABRIC_WEB_REGION", "ru-ru")
_WEB_MAX_RETRIES = int(os.environ.get("HFABRIC_WEB_RETRIES", "3"))


def _hash(text: str) -> str:
    return hashlib.sha1(text.encode("utf-8", "ignore")).hexdigest()[:10]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _http_get_json(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    timeout: float = 12.0,
) -> dict | None:
    try:
        import httpx

        with httpx.Client(timeout=timeout) as client:
            r = client.get(url, headers=headers or {}, params=params or {})
            if r.status_code >= 400:
                _log.warning("http_get_json %s -> HTTP %s", url, r.status_code)
                return None
            return r.json()
    except Exception as exc:
        _log.warning("http_get_json %s failed: %s", url, exc)
        return None


def _http_post_json(
    url: str,
    *,
    json_body: dict | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 12.0,
) -> dict | None:
    try:
        import httpx

        with httpx.Client(timeout=timeout) as client:
            r = client.post(url, json=json_body or {}, headers=headers or {})
            if r.status_code >= 400:
                _log.warning("http_post_json %s -> HTTP %s", url, r.status_code)
                return None
            return r.json()
    except Exception as exc:
        _log.warning("http_post_json %s failed: %s", url, exc)
        return None


def _http_get_text(
    url: str,
    *,
    headers: dict[str, str] | None = None,
    params: dict[str, str] | None = None,
    timeout: float = 12.0,
) -> str | None:
    try:
        import httpx

        with httpx.Client(timeout=timeout) as client:
            r = client.get(url, headers=headers or {}, params=params or {})
            if r.status_code >= 400:
                _log.warning("http_get_text %s -> HTTP %s", url, r.status_code)
                return None
            return r.text
    except Exception as exc:
        _log.warning("http_get_text %s failed: %s", url, exc)
        return None


def web_search(query: str, top_k: int = 8) -> list[EvidenceChunk]:
    results: list[EvidenceChunk] = []
    last_exc: Exception | None = None
    for attempt in range(_WEB_MAX_RETRIES):
        try:
            from ddgs import DDGS

            backend = _WEB_BACKENDS[min(attempt, len(_WEB_BACKENDS) - 1)]
            with DDGS() as ddgs:
                hits = list(ddgs.text(
                    query,
                    region=_WEB_REGION,
                    safesearch="moderate",
                    max_results=top_k,
                    backend=backend,
                ))
            if hits:
                last_exc = None
                break
            _log.info("web_search attempt %d/%d backend=%s: 0 hits, retrying", attempt + 1, _WEB_MAX_RETRIES, backend)
        except Exception as exc:
            last_exc = exc
            _log.warning("web_search attempt %d/%d backend=%s failed: %s", attempt + 1, _WEB_MAX_RETRIES, _WEB_BACKENDS[min(attempt, len(_WEB_BACKENDS) - 1)], exc)
            time.sleep(0.5 * (attempt + 1))
    else:
        if last_exc is not None:
            _log.warning("web_search exhausted %d retries: %s", _WEB_MAX_RETRIES, last_exc)
        else:
            _log.warning("web_search exhausted %d retries: no hits", _WEB_MAX_RETRIES)
        return results

    for hit in hits:
        url = hit.get("href") or hit.get("url") or hit.get("link") or ""
        title = hit.get("title", "").strip()
        snippet = (hit.get("body") or hit.get("snippet") or "").strip()
        if not url:
            continue
        cid = f"web:{_hash(url)}"
        text = f"{title}. {snippet}".strip(". ").strip()
        results.append(EvidenceChunk(
            chunk_id=cid,
            doc_id=cid,
            text=text or title or url,
            meta={
                "url": url,
                "title": title,
                "source": "web",
                "retrieved_at": _now(),
            },
        ))
    _log.info("web_search query=%r hits=%d", query[:80], len(results))
    return results


def materials_project_search(query: str, top_k: int = 5, api_key: str | None = None) -> list[EvidenceChunk]:
    key = api_key or os.environ.get("MP_API_KEY") or os.environ.get("PMG_MAPI_KEY")
    if not key:
        _log.warning(
            "MP_API_KEY not set — skipping Material Project search. "
            "Get a free key at https://next-gen.materialsproject.org/dashboard"
        )
        return []
    results: list[EvidenceChunk] = []
    try:
        from mp_api.client import MPRester

        keywords = [tok for tok in re.split(r"\W+", query) if len(tok) > 2][:8]
        with MPRester(key, mute_progress_bars=True) as mpr:
            try:
                docs = mpr.materials.synthesis.search(
                    keywords=keywords,
                    num_chunks=1,
                    chunk_size=top_k,
                )
            except Exception:
                elements = [tok for tok in re.split(r"\W+", query) if tok and tok[0].isupper() and 1 <= len(tok) <= 2]
                docs = mpr.materials.summary.search(
                    elements=elements or None,
                    num_chunks=1,
                    chunk_size=top_k,
                    fields=["material_id", "formula_pretty", "band_gap", "density"],
                )
        for doc in list(docs)[:top_k]:
            mid = str(getattr(doc, "material_id", "") or getattr(doc, "id", ""))
            if not mid:
                continue
            formula = getattr(doc, "formula_pretty", "") or getattr(doc, "target_formula", "")
            band_gap = getattr(doc, "band_gap", None)
            density = getattr(doc, "density", None)
            url = f"https://next-gen.materialsproject.org/materials/{mid}"
            text_bits = [f"Materials Project {formula} ({mid})"]
            if band_gap is not None:
                text_bits.append(f"band_gap={band_gap}")
            if density is not None:
                text_bits.append(f"density={density}")
            results.append(EvidenceChunk(
                chunk_id=f"mp:{mid}",
                doc_id=f"mp:{mid}",
                text=", ".join(text_bits) + ".",
                meta={
                    "url": url,
                    "title": f"{formula} — Materials Project",
                    "source": "mp",
                    "retrieved_at": _now(),
                },
            ))
    except Exception as exc:
        _log.warning("materials_project_search failed: %s", exc)
        return results
    _log.info("materials_project_search query=%r hits=%d", query[:80], len(results))
    return results


def citrination_search(
    query: str,
    top_k: int = 5,
    api_key: str | None = None,
    base_url: str | None = None,
    http_post: Callable[..., dict | None] | None = None,
) -> list[EvidenceChunk]:
    key = api_key or os.environ.get("CITRINATION_API_KEY")
    base = (base_url or os.environ.get("CITRINATION_BASE_URL") or "https://citrination.com").rstrip("/")
    if not key:
        _log.warning(
            "CITRINATION_API_KEY not set — skipping Citrination search. "
            "Get a key at https://citrination.com"
        )
        return []
    post = http_post or _http_post_json
    results: list[EvidenceChunk] = []
    body = {
        "query": {"query_string": {"query": query}},
        "size": top_k,
        "start": 0,
    }
    data = post(
        f"{base}/api/v2/search/pif",
        json_body=body,
        headers={"X-API-Key": key},
        timeout=12.0,
    )
    if not isinstance(data, dict):
        _log.warning("citrination_search: no data returned")
        return results
    hits = data.get("results") or data.get("hits") or []
    for hit in hits[:top_k]:
        sample = hit.get("sample") or hit.get("_source", {}).get("sample") or {}
        name = sample.get("name") or hit.get("name") or "Citrination sample"
        formula = sample.get("chemicalFormula") or ""
        cid_val = hit.get("id") or hit.get("uid") or _hash(name + str(formula))
        url = hit.get("url") or f"{base}/samples/{cid_val}"
        props = sample.get("properties", [])
        prop_text = "; ".join(
            f"{p.get('name','?')}={p.get('scalars', [{}])[0].get('value','?') if p.get('scalars') else '?'}"
            for p in (props or [])[:5]
        )
        results.append(EvidenceChunk(
            chunk_id=f"cit:{_hash(str(cid_val))}",
            doc_id=f"cit:{_hash(str(cid_val))}",
            text=f"{name} {formula} — {prop_text}".strip(" -"),
            meta={
                "url": url,
                "title": f"{name} — Citrination",
                "source": "citrination",
                "retrieved_at": _now(),
            },
        ))
    _log.info("citrination_search query=%r hits=%d", query[:80], len(results))
    return results


_NIMS_LINK_RE = re.compile(r'<a[^>]*href="([^"]+)"[^>]*>([^<]+)</a>', re.IGNORECASE)


def nims_matnavi_search(
    query: str,
    top_k: int = 5,
    base_url: str | None = None,
    http_get_text: Callable[..., str | None] | None = None,
) -> list[EvidenceChunk]:
    base = (base_url or os.environ.get("NIMS_MATNAVI_BASE_URL") or "https://mits.nims.go.jp").rstrip("/")
    get_text = http_get_text or _http_get_text
    results: list[EvidenceChunk] = []
    for path in ("/search", "/list/search", "/index_en.html"):
        html = get_text(
            f"{base}{path}",
            params={"q": query, "lang": "en", "keyword": query},
            headers={"Accept": "text/html"},
            timeout=12.0,
        )
        if html:
            break
    if not html:
        _log.warning("nims_matnavi_search: no HTML returned (NIMS may be offline or path moved)")
        return results

    seen: set[str] = set()
    for href, label in _NIMS_LINK_RE.findall(html):
        href = href.strip()
        label = label.strip()
        if not href or href.startswith("#") or href.startswith("javascript:"):
            continue
        if not any(t in label.lower() for t in query.lower().split() if len(t) > 2):
            continue
        full = href if href.startswith("http") else f"{base}/{href.lstrip('/')}"
        if full in seen:
            continue
        seen.add(full)
        if len(results) >= top_k:
            break
        results.append(EvidenceChunk(
            chunk_id=f"nims:{_hash(full)}",
            doc_id=f"nims:{_hash(full)}",
            text=label,
            meta={
                "url": full,
                "title": label,
                "source": "nims_matnavi",
                "retrieved_at": _now(),
            },
        ))
    _log.info("nims_matnavi_search query=%r hits=%d", query[:80], len(results))
    return results


_LEGACY_MODE_MAP = {
    "none": [],
    "web": ["web"],
    "web+mp": ["web", "mp"],
    "all": ["web", "mp", "citrination", "nims"],
}


def _parse_sources(mode: str) -> list[str]:
    if not mode:
        return ["web"]
    if mode in _LEGACY_MODE_MAP:
        return _LEGACY_MODE_MAP[mode]
    sources = [s.strip() for s in mode.split(",") if s.strip()]
    valid = {"web", "mp", "citrination", "nims"}
    return [s for s in sources if s in valid] or ["web"]


def _extract_entities(candidates: list[Any], limit: int = 6) -> list[str]:
    counts: dict[str, int] = {}
    for scored in candidates:
        text = ""
        if hasattr(scored, "hypothesis"):
            h = scored.hypothesis
            text = f"{h.claim} {h.mechanism}"
        elif isinstance(scored, dict):
            h = scored.get("hypothesis", {})
            text = f"{h.get('claim', '')} {h.get('mechanism', '')}"
        for tok in re.findall(r"[A-ZА-Я][a-zа-я]{3,}|[A-Z][a-z]?\b", text):
            key = tok.strip()
            if len(key) >= 2:
                counts[key] = counts.get(key, 0) + 1
    ranked = sorted(counts.items(), key=lambda kv: -kv[1])
    return [k for k, _ in ranked[:limit]]


def _run_source(source: str, query: str, top_k: int) -> list[EvidenceChunk]:
    try:
        if source == "web":
            return web_search(query, top_k=top_k)
        if source == "mp":
            return materials_project_search(query, top_k=max(2, top_k // 2))
        if source == "citrination":
            return citrination_search(query, top_k=max(2, top_k // 2))
        if source == "nims":
            return nims_matnavi_search(query, top_k=max(2, top_k // 2))
    except Exception as exc:
        _log.warning("source=%s failed: %s", source, exc)
    return []


def gather_external(
    kpi: KPIParsed,
    candidates: list[Any],
    config: Any,
) -> list[EvidenceChunk]:
    sources = _parse_sources(getattr(config, "external_search", "web"))
    if not sources:
        _log.info("external_search disabled (mode=none)")
        return []

    top_k = getattr(config, "external_top_k", 8)
    entities = _extract_entities(candidates)
    query = " ".join(filter(None, [kpi.kpi.metric, kpi.goal] + entities[:4]))
    query = query.strip() or kpi.goal
    _log.info("gather_external: sources=%s query=%r top_k=%d", sources, query[:100], top_k)

    chunks: list[EvidenceChunk] = []
    with ThreadPoolExecutor(max_workers=min(4, len(sources))) as pool:
        future_to_source = {
            pool.submit(_run_source, src, query, top_k): src for src in sources
        }
        for fut in as_completed(future_to_source, timeout=45):
            src = future_to_source[fut]
            try:
                chunks.extend(fut.result())
            except FuturesTimeout:
                _log.warning("source=%s timed out", src)
            except Exception as exc:
                _log.warning("source=%s future failed: %s", src, exc)

    seen: set[str] = set()
    deduped: list[EvidenceChunk] = []
    for c in chunks:
        url = c.meta.get("url", c.chunk_id)
        if url in seen:
            continue
        seen.add(url)
        deduped.append(c)
    _log.info("gather_external done: %d unique chunks (from %d raw)", len(deduped), len(chunks))
    return deduped
