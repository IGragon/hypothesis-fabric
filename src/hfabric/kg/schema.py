from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path


DEFAULT_NODE_LABELS: set[str] = {"Material", "Property", "Parameter", "Process", "Source"}
DEFAULT_EDGE_TYPES: set[str] = {"influences", "measured_as", "composed_of", "contradicts"}

# Backward-compatible module-level constants used by kg/client.py and tests.
NODE_LABELS = DEFAULT_NODE_LABELS
EDGE_TYPES = DEFAULT_EDGE_TYPES


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
    ("element_ru", re.compile(
        r"\b(золот\w*|серебр\w*|никел\w*|мед[ьи]|платин\w*|паллади\w*|желез\w*|"
        r"цинк\w*|свинц\w*|кобальт\w*|молибден\w*|вольфрам\w*|алюмини\w*|хром\w*|марганц\w*|титан\w*)\b",
        re.IGNORECASE,
    )),
    ("mineral_ru", re.compile(
        r"\b(пирит\w*|халькопирит\w*|сфалерит\w*|галенит\w*|пентландит\w*|магнетит\w*|"
        r"гематит\w*|кварц\w*|кальцит\w*|доломит\w*|борнит\w*|халькозин\w*|ковеллит\w*|"
        r"арсенопирит\w*|пирротин\w*|молибденит\w*)\b",
        re.IGNORECASE,
    )),
    ("reagent_ru", re.compile(
        r"\b(ксантогенат\w*|собирател\w*|вспенивател\w*|депрессор\w*|активатор\w*|"
        r"цианид\w*|извест\w*|МИБК|медн\w*\s+купорос\w*|жидк\w*\s+стекл\w*)\b",
        re.IGNORECASE,
    )),
]

_PROPERTY_PATTERNS: list[tuple[str, re.Pattern]] = [
    ("recovery", re.compile(
        r"(\w+\s+)?(recovery|grade|yield)(\s+of\s+\w+)?\s*(?::|of|is|at|was|≈|~|=)?\s*(\d+[.,]?\d*\s*%?)",
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
    ("recovery_ru", re.compile(
        r"\b(извлечени\w*|содержани\w*)\b.*?(\d+[.,]?\d*\s*%?)",
        re.IGNORECASE,
    )),
    ("pH_ru", re.compile(
        r"\b(рН)\b.*?(\d+[.,]?\d*)",
        re.IGNORECASE,
    )),
    ("size_ru", re.compile(
        r"\b(крупност\w*)\b.*?(\d+[.,]?\d*\s*(?:мкм|мм|µm|μm|mm|mesh)?)",
        re.IGNORECASE,
    )),
    ("density_ru", re.compile(
        r"\b(плотност\w*|удельн\w*\s+вес\w*)\b.*?(\d+[.,]?\d*\s*(?:г/см³|кг/м³|g/cm³|kg/m³)?)",
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
    ("dosage_ru", re.compile(
        r"\b(расход\w*|дозировк\w*|концентраци\w*)\b.*?(\d+[.,]?\d*\s*(?:г/т|кг/т|мг/л|ppm|%|M)?)",
        re.IGNORECASE,
    )),
    ("temperature_ru", re.compile(
        r"\b(температур\w*)\b.*?(\d+[.,]?\d*\s*(?:°?C|°?F|K)?)",
        re.IGNORECASE,
    )),
    ("time_ru", re.compile(
        r"\b(врем\w*)\b.*?(\d+[.,]?\d*\s*(?:мин|с|ч|час|min|s|h|hr)?)",
        re.IGNORECASE,
    )),
    ("pulp_density_ru", re.compile(
        r"\b(плотност\w*\s+пульп\w*|содержани\w*\s+твёрд\w*|твёрд\w*)\b.*?(\d+[.,]?\d*\s*%?)",
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
    ("flotation_ru", re.compile(
        r"\b(флотаци\w*|основн\w*\s+флотаци|контрольн\w*\s+флотаци|перечист\w*|"
        r"колонн\w*\s+флотаци|камер\w*\s+Джеймсон|механическ\w*\s+камер\w*|флотомашин\w*)\b",
        re.IGNORECASE,
    )),
    ("leaching_ru", re.compile(
        r"\b(выщелачиван\w*|сорбцион\w*\s+выщелачиван|кучн\w*\s+выщелачиван|"
        r"автоклав\w*\s+выщелачиван|биоокислени\w*)\b",
        re.IGNORECASE,
    )),
    ("comminution_ru", re.compile(
        r"\b(измельчен\w*|дроблен\w*|мельниц\w*|ПСИ|полусамоизмельчен\w*|"
        r"шар\w*\s+мельниц\w*|стержн\w*\s+мельниц\w*|валк\w*\s+дробил\w*)\b",
        re.IGNORECASE,
    )),
    ("dewatering_ru", re.compile(
        r"\b(сгущен\w*|фильтрац\w*|обезвоживан\w*|хвост\w*|"
        r"классификац\w*|пастов\w*\s+сгустител\w*|фильтр-пресс\w*)\b",
        re.IGNORECASE,
    )),
]


def _default_patterns() -> dict[str, list[tuple[str, re.Pattern]]]:
    return {
        "Material": list(_MATERIAL_PATTERNS),
        "Property": list(_PROPERTY_PATTERNS),
        "Parameter": list(_PARAMETER_PATTERNS),
        "Process": list(_PROCESS_PATTERNS),
    }


@dataclass
class KGSchema:
    node_labels: set[str] = field(default_factory=lambda: set(DEFAULT_NODE_LABELS))
    edge_types: set[str] = field(default_factory=lambda: set(DEFAULT_EDGE_TYPES))
    patterns: dict[str, list[tuple[str, re.Pattern]]] = field(default_factory=_default_patterns)


def _compile_pattern_entry(sublabel: str, raw: str) -> tuple[str, re.Pattern]:
    flags = re.IGNORECASE
    return sublabel, re.compile(raw, flags)


def _patterns_from_yaml(label: str, raw) -> list[tuple[str, re.Pattern]]:
    out: list[tuple[str, re.Pattern]] = []
    if not isinstance(raw, list):
        return out
    for item in raw:
        if isinstance(item, str):
            out.append(_compile_pattern_entry(item, item))
        elif isinstance(item, dict):
            for sub, pat in item.items():
                out.append(_compile_pattern_entry(str(sub), str(pat)))
        elif isinstance(item, (list, tuple)) and len(item) == 2:
            out.append(_compile_pattern_entry(str(item[0]), str(item[1])))
    return out


def load_schema(path: str | None = None) -> KGSchema:
    schema = KGSchema()
    if not path:
        return schema

    p = Path(path)
    if not p.is_file():
        return schema

    try:
        import yaml

        data = yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    except Exception:
        return schema

    if isinstance(data, dict):
        nodes = data.get("node_labels")
        if isinstance(nodes, list):
            schema.node_labels = set(str(n) for n in nodes) | {"Source"}
        edges = data.get("edge_types")
        if isinstance(edges, list):
            schema.edge_types = set(str(e) for e in edges)
        patterns = data.get("patterns")
        if isinstance(patterns, dict):
            for label, raw in patterns.items():
                compiled = _patterns_from_yaml(str(label), raw)
                if compiled:
                    schema.patterns[str(label)] = compiled
    return schema