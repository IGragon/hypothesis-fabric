from __future__ import annotations

import re

from hfabric.kg.schema import _default_patterns

_RU_ENDINGS = (
    "ые", "ой", "ая", "ое", "ию", "ия", "ие", "ий", "ым", "ом", "ах", "ях",
    "ов", "ев", "ам", "ям", "ами", "ями", "ах", "ть", "ти", "нный", "нная",
    "нное", "нные", "нным", "нного", "нных", "тель", "ция", "ции", "цию",
    "циях", "циям", "циями", "ский", "ская", "ское", "ские", "ским",
    "ского", "ских", "ность", "ности", "ностью", "ностей", "емый", "аемая",
    "аемое", "аемые", "ающего", "ающей", "ающего", "вшая", "вший", "вшее",
    "вшие", "нна", "нно", "нны", "ннен", "на", "но", "ны", "ен", "ет",
    "ют", "ят", "ит", "ат", "ал", "ала", "ало", "али", "ил", "ила", "ило",
    "или", "ул", "ула", "уло", "ули", "ил", "ила", "ило", "или",
)

_EN_ENDINGS = ("ing", "ed", "tion", "sion", "ment", "ness", "ity", "ies", "ies", "ous", "ive", "ical", "ally")

_CANONICAL_MAP = {
    "au": "gold", "золот": "gold", "золота": "gold", "золоту": "gold",
    "ag": "silver", "серебр": "silver", "серебра": "silver", "серебру": "silver",
    "cu": "copper", "мед": "copper", "меди": "copper", "медь": "copper", "медью": "copper",
    "ni": "nickel", "никел": "nickel", "никеля": "nickel", "никелю": "nickel",
    "fe": "iron", "желез": "iron", "железа": "iron", "железу": "iron",
    "zn": "zinc", "цинк": "zinc", "цинка": "zinc", "цинку": "zinc",
    "pb": "lead", "свинц": "lead", "свинца": "lead", "свинцу": "lead",
    "pt": "platinum", "платин": "platinum", "платины": "platinum",
    "pd": "palladium", "паллади": "palladium", "палладия": "palladium",
    "co": "cobalt", "кобальт": "cobalt", "кобальта": "cobalt",
}


def _canonicalize(name: str) -> str:
    lower = name.strip().lower()
    if not lower:
        return lower
    if lower in _CANONICAL_MAP:
        return _CANONICAL_MAP[lower]
    if len(lower) <= 3:
        return lower
    for ending in _RU_ENDINGS:
        if lower.endswith(ending) and len(lower) > len(ending) + 2:
            lower = lower[: -len(ending)]
            break
    if len(lower) > 5:
        for ending in _EN_ENDINGS:
            if lower.endswith(ending) and len(lower) > len(ending) + 3:
                lower = lower[: -len(ending)]
                break
    if len(lower) > 5 and re.search(r"[а-я]", lower):
        lower = lower[:5]
    elif len(lower) > 4 and re.search(r"[a-z]", lower):
        lower = lower[:4]
    return lower

_DEFAULT_PATTERNS = _default_patterns()
_MATERIAL_PATTERNS = _DEFAULT_PATTERNS["Material"]
_PROPERTY_PATTERNS = _DEFAULT_PATTERNS["Property"]
_PARAMETER_PATTERNS = _DEFAULT_PATTERNS["Parameter"]
_PROCESS_PATTERNS = _DEFAULT_PATTERNS["Process"]


def _extract_category(text: str, patterns: list[tuple[str, re.Pattern]], label: str) -> list[dict]:
    entities: list[dict] = []
    seen: set[str] = set()

    for sublabel, pattern in patterns:
        for match in pattern.finditer(text):
            raw_name = match.group(0).strip()
            if len(raw_name) > 60:
                continue
            canonical = _canonicalize(raw_name)
            if not canonical or len(canonical) < 2:
                continue
            key = f"{label}:{sublabel}:{canonical}"
            if key in seen:
                continue
            seen.add(key)

            props: dict = {
                "name": canonical,
                "display_name": raw_name,
                "category": sublabel,
            }
            if len(match.groups()) >= 2:
                props["value"] = match.group(len(match.groups()))

            entities.append({
                "label": label,
                "properties": props,
            })

    return entities


def extract_entities(text: str, patterns: dict[str, list[tuple[str, "re.Pattern"]]] | None = None) -> list[dict]:
    pats = patterns if patterns is not None else _DEFAULT_PATTERNS
    entities: list[dict] = []
    for label, cat_patterns in pats.items():
        entities.extend(_extract_category(text, cat_patterns, label))
    return entities


def extract_edges(chunks: list[dict], patterns: dict[str, list[tuple[str, "re.Pattern"]]] | None = None) -> list[dict]:
    edges: list[dict] = []
    seen_pairs: set[tuple[str, str, str, str]] = set()

    for chunk in chunks:
        chunk_text = chunk.get("text", "")
        entities = extract_entities(chunk_text, patterns=patterns)

        for i in range(len(entities)):
            for j in range(i + 1, len(entities)):
                ei = entities[i]
                ej = entities[j]
                li = ei["label"]
                lj = ej["label"]
                if li == lj:
                    continue
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


def detect_contradictions(chunks: list[dict]) -> list[dict]:
    contradictions: list[dict] = []
    if len(chunks) > 100:
        return contradictions
    directional_pairs = [
        ("increase", "decrease"),
        ("повышает", "снижает"),
        ("увеличивает", "уменьшает"),
        ("higher", "lower"),
        ("выше", "ниже"),
        ("positive", "negative"),
        ("положительный", "отрицательный"),
        ("улучшает", "ухудшает"),
        ("improves", "degrades"),
        ("повышается", "снижается"),
        ("increases", "decreases"),
    ]

    all_words = [w for pair in directional_pairs for w in pair]
    all_words_lower = [w.lower() for w in all_words]

    chunk_entities = []
    chunk_texts_lower = []
    for chunk in chunks:
        text_lower = chunk.get("text", "").lower()
        chunk_texts_lower.append(text_lower)
        chunk_entities.append(extract_entities(text_lower))

    for i in range(len(chunks)):
        text_i = chunk_texts_lower[i]
        entities_i = chunk_entities[i]
        has_dir_i = {}
        for pair in directional_pairs:
            has_dir_i[pair[0]] = _has_word_stem(text_i, pair[0])

        for j in range(i + 1, len(chunks)):
            overlap = _find_entity_overlap(entities_i, chunk_entities[j])
            if not overlap:
                continue

            text_j = chunk_texts_lower[j]
            for dir_a, dir_b in directional_pairs:
                if has_dir_i[dir_a] and _has_word_stem(text_j, dir_b):
                    ci = chunks[i].get("chunk_id", "")
                    cj = chunks[j].get("chunk_id", "")
                    contradictions.append({
                        "from_label": "Source",
                        "from_name": ci,
                        "to_label": "Source",
                        "to_name": cj,
                        "rel_type": "contradicts",
                        "provenance": {"entity": overlap},
                    })
                    break
                elif _has_word_stem(text_j, dir_a) and _has_word_stem(text_i, dir_b):
                    ci = chunks[i].get("chunk_id", "")
                    cj = chunks[j].get("chunk_id", "")
                    contradictions.append({
                        "from_label": "Source",
                        "from_name": ci,
                        "to_label": "Source",
                        "to_name": cj,
                        "rel_type": "contradicts",
                        "provenance": {"entity": overlap},
                    })
                    break

    return contradictions


def _has_word_stem(text: str, stem: str) -> bool:
    for prefix in (stem, stem[:-1], stem[:-2]):
        if len(prefix) < 3:
            continue
        if bool(re.search(rf"\b{re.escape(prefix)}\w*", text, re.IGNORECASE)):
            return True
    return False


def _find_entity_overlap(entities_a: list[dict], entities_b: list[dict]) -> str:
    names_a = {
        (e["label"], e["properties"]["name"].lower()) for e in entities_a
        if "name" in e["properties"]
    }
    names_b = {
        (e["label"], e["properties"]["name"].lower()) for e in entities_b
        if "name" in e["properties"]
    }
    overlap = names_a & names_b
    if overlap:
        first = next(iter(overlap))
        return f"{first[0]}:{first[1]}"
    return ""
