from __future__ import annotations

from hfabric.retriever.query_plan import build_query_plan
from hfabric.schemas import KPI, KPIParsed


def test_build_query_plan_goal_only():
    kpi = KPIParsed(
        goal="increase Au flotation recovery",
        kpi=KPI(metric="recovery", direction="increase", target="5%"),
        constraints=[],
        language="en",
    )
    plan = build_query_plan(kpi)
    assert plan["query_text"] == "query: increase Au flotation recovery"
    assert "increase" in plan["keywords"]
    assert "au" in plan["keywords"]
    assert "flotation" in plan["keywords"]
    assert "recovery" in plan["keywords"]


def test_build_query_plan_with_constraints():
    kpi = KPIParsed(
        goal="increase Au flotation recovery by 5%",
        kpi=KPI(metric="recovery", direction="increase", target="5%"),
        constraints=["without raising cyanide use", "no environmental harm"],
        language="en",
    )
    plan = build_query_plan(kpi)
    assert "query: increase Au flotation recovery by 5% without raising cyanide use no environmental harm" == plan["query_text"]
    assert "cyanide" in plan["keywords"]
    assert "environmental" in plan["keywords"]


def test_build_query_plan_kg_entities():
    kpi = KPIParsed(
        goal="increase Au flotation recovery using Xanthate collectors",
        kpi=KPI(metric="recovery", direction="increase", target="5%"),
        constraints=["no Sodium cyanide"],
        language="en",
    )
    plan = build_query_plan(kpi)
    assert "Au" in plan["kg_entities"]
    assert "Xanthate" in plan["kg_entities"]
    assert "Sodium" in plan["kg_entities"]
    assert "flotation" in plan["kg_entities"]


def test_build_query_plan_chemical_formulas():
    kpi = KPIParsed(
        goal="study effect of Na2S on Au flotation",
        kpi=KPI(metric="recovery", direction="increase", target="3%"),
        constraints=["with H2SO4 pre-treatment"],
        language="en",
    )
    plan = build_query_plan(kpi)
    assert "Na2S" in plan["kg_entities"]
    assert "H2SO4" in plan["kg_entities"]
    assert "Au" in plan["kg_entities"]


def test_build_query_plan_skip_words():
    kpi = KPIParsed(
        goal="increase the recovery of gold",
        kpi=KPI(metric="recovery", direction="increase", target="2%"),
        constraints=[],
        language="en",
    )
    plan = build_query_plan(kpi)
    assert "the" not in plan["keywords"]
    assert "of" not in plan["keywords"]
    assert "gold" in plan["keywords"]
    assert "recovery" in plan["keywords"]


def test_build_query_plan_process_terms():
    kpi = KPIParsed(
        goal="optimize flotation and leaching processes",
        kpi=KPI(metric="efficiency", direction="increase", target="10%"),
        constraints=[],
        language="en",
    )
    plan = build_query_plan(kpi)
    assert "flotation" in plan["kg_entities"]
    assert "leaching" in plan["kg_entities"]
