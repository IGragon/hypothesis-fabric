from __future__ import annotations

import types

import pytest

from hfabric.retriever import external
from hfabric.retriever.external import (
    citrination_search,
    gather_external,
    nims_matnavi_search,
    _parse_sources,
)
from hfabric.schemas import KPI, KPIParsed


def _kpi(metric: str = "Au recovery", goal: str = "increase Au recovery") -> KPIParsed:
    return KPIParsed(
        goal=goal,
        kpi=KPI(metric=metric, direction="increase", target="+15%"),
        constraints=["use xanthate"],
        language="en",
    )


class _Cfg:
    def __init__(self, mode="web", top_k=4):
        self.external_search = mode
        self.external_top_k = top_k


class TestParseSources:
    def test_none(self):
        assert _parse_sources("none") == []

    def test_web(self):
        assert _parse_sources("web") == ["web"]

    def test_legacy_web_plus_mp(self):
        assert _parse_sources("web+mp") == ["web", "mp"]

    def test_all(self):
        assert _parse_sources("all") == ["web", "mp", "citrination", "nims"]

    def test_csv_list(self):
        assert _parse_sources("web,mp,citrination,nims") == ["web", "mp", "citrination", "nims"]

    def test_csv_list_partial(self):
        assert _parse_sources("web,citrination") == ["web", "citrination"]

    def test_invalid_tokens_filtered_to_web_default(self):
        assert _parse_sources("web,foo,bar") == ["web"]

    def test_empty_defaults_to_web(self):
        assert _parse_sources("") == ["web"]


class TestCitrinationSearch:
    def test_no_api_key_returns_empty(self, monkeypatch):
        monkeypatch.delenv("CITRINATION_API_KEY", raising=False)
        assert citrination_search("gold recovery") == []

    def test_parses_pif_hits_into_evidence_chunks(self, monkeypatch):
        monkeypatch.setenv("CITRINATION_API_KEY", "test-key")
        captured: dict = {}

        def fake_post(url, *, json_body=None, headers=None, timeout=8.0):
            captured["url"] = url
            captured["headers"] = headers
            captured["body"] = json_body
            return {
                "results": [
                    {
                        "id": "abc1",
                        "url": "https://citrination.com/samples/abc1",
                        "name": "Gold ore sample",
                        "sample": {
                            "name": "Gold ore sample",
                            "chemicalFormula": "Au",
                            "properties": [
                                {"name": "density", "scalars": [{"value": 19.3}]},
                                {"name": "band_gap", "scalars": [{"value": 0.0}]},
                            ],
                        },
                    },
                    {
                        "id": "abc2",
                        "name": "Pentlandite",
                        "sample": {"name": "Pentlandite", "chemicalFormula": "(Fe,Ni)9S8", "properties": []},
                    },
                ]
            }

        chunks = citrination_search("gold", top_k=5, http_post=fake_post)
        assert len(chunks) == 2
        assert chunks[0].chunk_id.startswith("cit:")
        assert chunks[0].meta["source"] == "citrination"
        assert chunks[0].meta["url"] == "https://citrination.com/samples/abc1"
        assert "density" in chunks[0].text
        assert "Au" in chunks[0].text
        assert "X-API-Key" in captured["headers"]
        assert captured["headers"]["X-API-Key"] == "test-key"
        assert captured["body"]["size"] == 5

    def test_graceful_when_api_returns_none(self, monkeypatch):
        monkeypatch.setenv("CITRINATION_API_KEY", "k")
        assert citrination_search("q", http_post=lambda *a, **k: None) == []

    def test_graceful_on_unexpected_shape(self, monkeypatch):
        monkeypatch.setenv("CITRINATION_API_KEY", "k")
        assert citrination_search("q", http_post=lambda *a, **k: {"unexpected": 1}) == []


class TestNimsMatnaviSearch:
    def test_parses_html_anchors(self, monkeypatch):
        html = (
            '<html><body>'
            '<a href="/materials/gold">Gold recovery data</a>'
            '<a href="https://other.example/x">Gold recovery data</a>'
            '<a href="#frag">Gold recovery data</a>'
            '<a href="/silver">Silver nanoparticle</a>'
            '</body></html>'
        )
        chunks = nims_matnavi_search(
            "gold recovery", top_k=5,
            http_get_text=lambda url, *, headers=None, params=None, timeout=8.0: html,
        )
        urls = {c.meta["url"] for c in chunks}
        assert "https://mits.nims.go.jp/materials/gold" in urls
        assert all("silver" not in c.text.lower() for c in chunks)

    def test_skips_fragment_and_javascript(self):
        html = '<a href="#frag">gold recovery</a><a href="javascript:foo()">gold recovery</a>'
        chunks = nims_matnavi_search("gold recovery", http_get_text=lambda *a, **k: html)
        assert chunks == []

    def test_graceful_on_request_failure(self):
        assert nims_matnavi_search("gold", http_get_text=lambda *a, **k: None) == []

    def test_dedups_duplicate_urls(self):
        html = (
            '<a href="/m1">gold recovery data</a>'
            '<a href="/m1">gold recovery data duplicate</a>'
        )
        chunks = nims_matnavi_search("gold recovery", http_get_text=lambda *a, **k: html)
        assert len(chunks) == 1


class TestGatherExternal:
    def test_none_mode_returns_empty(self, monkeypatch):
        called: list[str] = []
        monkeypatch.setattr(external, "web_search", lambda q, top_k=8: called.append(q) or [])
        chunked = gather_external(_kpi(), [], _Cfg(mode="none"))
        assert chunked == []
        assert called == []

    def test_web_only_calls_web_search(self, monkeypatch):
        monkeypatch.setattr(external, "web_search", lambda q, top_k=8: [])
        monkeypatch.setattr(external, "materials_project_search", lambda q, top_k=5: [None])
        monkeypatch.setattr(external, "citrination_search", lambda q, top_k=2: [None])
        monkeypatch.setattr(external, "nims_matnavi_search", lambda q, top_k=2: [None])
        assert gather_external(_kpi(), [], _Cfg(mode="web")) == []

    def test_all_calls_all_four_searchers(self, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(external, "web_search", lambda q, top_k=8: calls.append("web") or [])
        monkeypatch.setattr(external, "materials_project_search", lambda q, top_k=2: calls.append("mp") or [])
        monkeypatch.setattr(external, "citrination_search", lambda q, top_k=2: calls.append("cit") or [])
        monkeypatch.setattr(external, "nims_matnavi_search", lambda q, top_k=2: calls.append("nims") or [])
        gather_external(_kpi(), [], _Cfg(mode="all"))
        assert calls == ["web", "mp", "cit", "nims"]

    def test_csv_mode_selective(self, monkeypatch):
        calls: list[str] = []
        monkeypatch.setattr(external, "web_search", lambda q, top_k=8: calls.append("web") or [])
        monkeypatch.setattr(external, "materials_project_search", lambda q, top_k=2: calls.append("mp") or [])
        monkeypatch.setattr(external, "citrination_search", lambda q, top_k=2: calls.append("cit") or [])
        monkeypatch.setattr(external, "nims_matnavi_search", lambda q, top_k=2: calls.append("nims") or [])
        gather_external(_kpi(), [], _Cfg(mode="web,nims"))
        assert calls == ["web", "nims"]

    def test_dedups_by_url(self, monkeypatch):
        from hfabric.schemas import EvidenceChunk

        chunk = EvidenceChunk(chunk_id="a", doc_id="a", text="t", meta={"url": "https://dup.example"})
        monkeypatch.setattr(external, "web_search", lambda q, top_k=8: [chunk])
        monkeypatch.setattr(external, "materials_project_search", lambda q, top_k=2: [chunk])
        result = gather_external(_kpi(), [], _Cfg(mode="web,mp"))
        assert len(result) == 1