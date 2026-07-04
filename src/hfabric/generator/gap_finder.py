from __future__ import annotations

from dataclasses import dataclass, field

from hfabric.contracts import KGProtocol
from hfabric.schemas import EvidenceChunk, Hypothesis, KPIParsed


@dataclass
class GapFinder:
    kg: KGProtocol
    min_neighbours: int = 2

    def find_gaps(self, kpi: KPIParsed, evidence: list[EvidenceChunk]) -> list[dict]:
        if not evidence:
            return []

        keywords = self._extract_keywords(kpi)
        if not keywords:
            return []

        gaps: list[dict] = []
        seen: set[str] = set()

        for chunk in evidence:
            text = chunk.text.lower()
            matched = [kw for kw in keywords if kw.lower() in text]
            if not matched:
                continue

            for kw in matched:
                try:
                    entities = self.kg.get_entities(kw)
                except Exception:
                    continue

                for entity in entities:
                    if entity.id in seen:
                        continue
                    seen.add(entity.id)

                    try:
                        neighbours = self.kg.neighbours(entity.id, hops=1)
                    except Exception:
                        neighbours = []

                    if len(neighbours) < self.min_neighbours:
                        gaps.append({
                            "entity_name": entity.properties.get("name", kw),
                            "entity_label": entity.label,
                            "neighbour_count": len(neighbours),
                            "matched_keyword": kw,
                        })

        return gaps

    def _extract_keywords(self, kpi: KPIParsed) -> list[str]:
        import re
        text = kpi.goal + " " + kpi.kpi.metric
        tokens = re.findall(r"[A-Za-zА-Яа-яёЁ]+", text)
        stop = {"the", "a", "an", "of", "in", "by", "to", "or", "and", "for", "with", "at", "is", "no", "not", "в", "и", "с", "на", "по", "от", "до", "без", "для"}
        keywords = [t for t in tokens if t.lower() not in stop and len(t) > 1]
        return list(dict.fromkeys(keywords))

    def generate(
        self,
        gaps: list[dict],
        evidence: list[EvidenceChunk],
        kpi: KPIParsed,
        llm=None,
    ) -> list[Hypothesis]:
        if not gaps or llm is None:
            return self._fallback_generate(gaps, kpi)

        evidence_text = "\n".join(
            f"[{c.chunk_id}] {c.text[:300]}" for c in evidence[:5]
        )
        gap_text = "\n".join(
            f"Gap: {g['entity_name']} ({g['entity_label']}) has only {g['neighbour_count']} connections"
            for g in gaps[:5]
        )

        prompt = (
            f"Goal: {kpi.goal}\n"
            f"Knowledge gaps found:\n{gap_text}\n\n"
            f"Relevant evidence:\n{evidence_text}\n\n"
            f"Generate research hypotheses that address these knowledge gaps. "
            f"For each hypothesis, provide: claim, mechanism, expected_effect, "
            f"and evidence_refs (list of chunk_ids from above). "
            f"Return valid JSON: [{{\"claim\": \"...\", \"mechanism\": \"...\", \"expected_effect\": \"...\", \"evidence_refs\": [\"...\"]}}]"
        )

        try:
            import json
            response = llm.invoke(prompt)
            content = response.content if hasattr(response, "content") else str(response)
            if isinstance(content, list):
                content = "".join(
                    item.get("text", "") if isinstance(item, dict) else str(item)
                    for item in content
                )

            parsed = json.loads(content)
            if not isinstance(parsed, list):
                return []

            return [
                Hypothesis(
                    claim=h.get("claim", ""),
                    mechanism=h.get("mechanism", ""),
                    expected_effect=h.get("expected_effect", ""),
                    evidence_refs=h.get("evidence_refs", []),
                )
                for h in parsed
                if h.get("claim")
            ]
        except Exception:
            return self._fallback_generate(gaps, kpi)

    def _fallback_generate(self, gaps: list[dict], kpi: KPIParsed) -> list[Hypothesis]:
        hypotheses: list[Hypothesis] = []
        for gap in gaps:
            claim = (
                f"Investigate the role of {gap['entity_name']} "
                f"({gap['entity_label']}) to improve {kpi.kpi.metric}"
            )
            mechanism = (
                f"The entity {gap['entity_name']} has only {gap['neighbour_count']} "
                f"known connections, suggesting unexplored mechanisms"
            )
            hypotheses.append(
                Hypothesis(
                    claim=claim,
                    mechanism=mechanism,
                    expected_effect=f"Potential improvement in {kpi.kpi.metric}",
                    evidence_refs=[],
                )
            )
        return hypotheses
