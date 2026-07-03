from __future__ import annotations

import re

_MATERIAL_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("element", re.compile(
        r"\b(gold|Au|silver|Ag|copper|Cu|iron|Fe|nickel|Ni|platinum|Pt|"
        r"palladium|Pd|zinc|Zn|lead|Pb|aluminium|Al|titanium|Ti|"
        r"chromium|Cr|manganese|Mn|cobalt|Co|molybdenum|Mo|tungsten|W)\b",
        re.IGNORECASE,
    )),
    ("mineral", re.compile(
        r"\b(pyrite|chalcopyrite|sphalerite|galena|pentlandite|magnetite|"
        r"hematite|quartz|calcite|dolomite|bornite|chalcocite|covellite|"
        r"arsenopyrite|pyrrhotite|molybdenite)\b",
        re.IGNORECASE,
    )),
    ("reagent", re.compile(
        r"\b(xanthate|PAX|SIBX|dithiophosphate|collector|frother|MIBC|"
        r"depressant|activator|cyanide|NaCN|lime|CaO|copper sulphate|CuSO4|"
        r"sodium sulphide|Na2S|sodium silicate|Na2SiO3|guar gum|"
        r"CMC|carboxymethyl cellulose)\b",
        re.IGNORECASE,
    )),
]

_PROPERTY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("recovery", re.compile(
        r"(\w+\s+)?(recovery|grade|yield)(\s+of\s+\w+)?\s*(?::|of|is|at|was|≈|~)?\s*(\d+[.,]?\d*\s*%?)",
        re.IGNORECASE,
    )),
    ("pH", re.compile(
        r"\b(pH)\s*(?::|of|is|at|was|≈|~|=)?\s*(\d+[.,]?\d*)",
        re.IGNORECASE,
    )),
    ("size", re.compile(
        r"\b(P\d+|d\d+)\s*(?::|of|is|at|≈|~|=)?\s*(\d+[.,]?\d*\s*(?:µm|μm|mm|mesh)?)",
        re.IGNORECASE,
    )),
    ("density", re.compile(
        r"\b(density|specific gravity|SG)\s*(?::|of|is|at|≈|~|=)?\s*(\d+[.,]?\d*\s*(?:g/cm³|kg/m³)?)",
        re.IGNORECASE,
    )),
]

_PARAMETER_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("dosage", re.compile(
        r"\b(dosage|dose|addition rate|concentration)\s*(?::|of|is|at|was|≈|~|=)?\s*(\d+[.,]?\d*\s*(?:g/t|kg/t|mg/L|ppm|%|M)?)",
        re.IGNORECASE,
    )),
    ("temperature", re.compile(
        r"\b(temperature|temp\.?)\s*(?::|of|is|at|was|≈|~|=)?\s*(\d+[.,]?\d*\s*(?:°?C|°?F|K)?)",
        re.IGNORECASE,
    )),
    ("time", re.compile(
        r"\b(residence time|conditioning time|flotation time|retention)\s*(?::|of|is|at|≈|~|=)?\s*(\d+[.,]?\d*\s*(?:min|s|h|hr)?)",
        re.IGNORECASE,
    )),
    ("flow_rate", re.compile(
        r"\b(flow rate|air flow|pulp flow)\s*(?::|of|is|at|≈|~|=)?\s*(\d+[.,]?\d*\s*(?:L/min|m³/h)?)",
        re.IGNORECASE,
    )),
    ("pulp_density", re.compile(
        r"\b(pulp density|solid[s]? content|% solids)\s*(?::|of|is|at|≈|~|=)?\s*(\d+[.,]?\d*\s*%?)",
        re.IGNORECASE,
    )),
]

_PROCESS_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("flotation", re.compile(
        r"\b(flotation|rougher|scavenger|cleaner|recleaner|"
        r"column flotation|Jameson cell|mechanical cell)\b",
        re.IGNORECASE,
    )),
    ("leaching", re.compile(
        r"\b(leaching|CIL|CIP|heap leach|tank leach|"
        r"pressure oxidation|POX|bio-oxidation|BIOX)\b",
        re.IGNORECASE,
    )),
    ("comminution", re.compile(
        r"\b(grinding|crushing|milling|SAG|ball mill|rod mill|"
        r"stirred mill|IsaMill|VertiMill|HPGR)\b",
        re.IGNORECASE,
    )),
    ("dewatering", re.compile(
        r"\b(thickening|filtration|dewatering|tailings|"
        r"paste thickener|filter press)\b",
        re.IGNORECASE,
    )),
]


def _extract_category(text: str, patterns: list[tuple[str, re.Pattern]], label: str) -> list[dict]:
    entities: list[dict] = []
    seen: set[str] = set()

    for sublabel, pattern in patterns:
        for match in pattern.finditer(text):
            name = match.group(0).strip()
            key = f"{label}:{sublabel}:{name.lower()}"
            if key in seen:
                continue
            seen.add(key)

            props: dict = {
                "name": name,
                "category": sublabel,
            }
            if len(match.groups()) >= 2:
                props["value"] = match.group(len(match.groups()))

            entities.append({
                "label": label,
                "properties": props,
            })

    return entities


def extract_entities(text: str) -> list[dict]:
    entities: list[dict] = []
    entities.extend(_extract_category(text, _MATERIAL_PATTERNS, "Material"))
    entities.extend(_extract_category(text, _PROPERTY_PATTERNS, "Property"))
    entities.extend(_extract_category(text, _PARAMETER_PATTERNS, "Parameter"))
    entities.extend(_extract_category(text, _PROCESS_PATTERNS, "Process"))
    return entities


def extract_edges(chunks: list[dict]) -> list[dict]:
    edges: list[dict] = []
    seen_pairs: set[tuple[str, str, str, str]] = set()

    for chunk in chunks:
        chunk_text = chunk.get("text", "")
        entities = extract_entities(chunk_text)

        for i in range(len(entities)):
            for j in range(i + 1, len(entities)):
                ei = entities[i]
                ej = entities[j]
                li = ei["label"]
                lj = ej["label"]
                ni = ei["properties"]["name"]
                nj = ej["properties"]["name"]

                rel_type = _infer_relation(li, lj)

                pair_key = (li, ni, lj, nj)
                pair_key_rev = (lj, nj, li, ni)

                if pair_key in seen_pairs or pair_key_rev in seen_pairs:
                    continue
                seen_pairs.add(pair_key)

                edges.append({
                    "from_label": li,
                    "from_name": ni,
                    "to_label": lj,
                    "to_name": nj,
                    "rel_type": rel_type,
                    "provenance": {
                        "chunk_id": chunk.get("chunk_id", ""),
                        "doc_id": chunk.get("meta", {}).get("doc_id", ""),
                    },
                })

    return edges


def _infer_relation(from_label: str, to_label: str) -> str:
    if from_label == "Process" or to_label == "Process":
        return "influences"
    if from_label == "Parameter" or to_label == "Parameter":
        return "influences"
    if (from_label == "Material" and to_label == "Property") or \
       (to_label == "Material" and from_label == "Property"):
        return "influences"
    return "influences"
