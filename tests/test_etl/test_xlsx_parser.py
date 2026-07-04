from __future__ import annotations

import os
import tempfile

from hfabric.etl.parser import parse_xlsx, _parse_tailings_xlsx

XLSX_TEST_DIR = os.path.join(
    os.path.dirname(__file__),
    "..", "..", "additional_material", "Пример 1",
)


class TestParseXlsx:
    def test_parse_tailings_xlsx(self):
        path = os.path.join(XLSX_TEST_DIR, "Хвосты КГМК.xlsx")
        if not os.path.exists(path):
            import pytest
            pytest.skip("XLSX test file not found")

        pages = parse_xlsx(path)
        assert len(pages) > 0, "Should extract at least one page"
        for page in pages:
            assert "text" in page
            assert "meta" in page
            assert len(page["text"]) > 0

    def test_tailings_contains_expected_terms(self):
        path = os.path.join(XLSX_TEST_DIR, "Хвосты КГМК.xlsx")
        if not os.path.exists(path):
            import pytest
            pytest.skip("XLSX test file not found")

        pages = parse_xlsx(path)
        full_text = "\n".join(p["text"] for p in pages).lower()
        assert "шихта руд" in full_text or "хвосты" in full_text
        assert "элемент 28" in full_text or "эл.28" in full_text
        assert "элемент 29" in full_text or "эл.29" in full_text

    def test_tailings_contains_size_classes(self):
        path = os.path.join(XLSX_TEST_DIR, "Хвосты КГМК.xlsx")
        if not os.path.exists(path):
            import pytest
            pytest.skip("XLSX test file not found")

        pages = parse_xlsx(path)
        full_text = "\n".join(p["text"] for p in pages).lower()
        size_classes = ["+125", "+71", "-71", "-45", "-20", "-10"]
        found = [sc for sc in size_classes if sc in full_text]
        assert len(found) >= 3, f"Should find at least 3 size classes, found: {found}"

    def test_tailings_recoverable_summary(self):
        path = os.path.join(XLSX_TEST_DIR, "Хвосты КГМК.xlsx")
        if not os.path.exists(path):
            import pytest
            pytest.skip("XLSX test file not found")

        pages = parse_xlsx(path)
        full_text = "\n".join(p["text"] for p in pages).lower()
        assert "извлекаемый металл" in full_text
        assert "не извлекаемый металл" in full_text

    def test_multiple_examples(self):
        for example in ["Пример 1", "Пример 2", "Пример 3", "Пример 4"]:
            import glob
            files = glob.glob(os.path.join(
                os.path.dirname(__file__), "..", "..", "additional_material", example, "*.xlsx"
            ))
            if not files:
                continue
            pages = parse_xlsx(files[0])
            assert len(pages) >= 1, f"{example}: should extract at least one page"
            combined = "\n".join(p["text"] for p in pages)
            assert len(combined) > 100, f"{example}: text too short"

    def test_tailings_contains_mineral_forms(self):
        path = os.path.join(XLSX_TEST_DIR, "Хвосты КГМК.xlsx")
        if not os.path.exists(path):
            import pytest
            pytest.skip("XLSX test file not found")

        pages = parse_xlsx(path)
        full_text = "\n".join(p["text"] for p in pages).lower()
        minerals = ["пентландит", "халькопирит", "пирротин", "миллерит"]
        found = [m for m in minerals if m in full_text]
        assert len(found) >= 2, f"Should find mineral forms, found: {found}"
