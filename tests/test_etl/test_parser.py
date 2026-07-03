from __future__ import annotations

import os
import tempfile

import pytest

from hfabric.etl.parser import parse_pdf


@pytest.fixture
def sample_pdf_path():
    import fitz

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        tmp_path = f.name

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Page one content. Gold flotation recovery is studied here.")
    page = doc.new_page()
    page.insert_text((72, 72), "Page two content. Cyanide consumption must be minimized.")
    page = doc.new_page()
    page.insert_text((72, 72), "")
    doc.save(tmp_path)
    doc.close()

    yield tmp_path

    os.unlink(tmp_path)


@pytest.fixture
def sample_pdf_single_page():
    import fitz

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        tmp_path = f.name

    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Xanthate collectors improve gold flotation recovery.")
    doc.save(tmp_path)
    doc.close()

    yield tmp_path

    os.unlink(tmp_path)


class TestParsePdf:
    def test_parse_pdf_returns_list_of_dicts(self, sample_pdf_path):
        result = parse_pdf(sample_pdf_path)
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(p, dict) for p in result)

    def test_parse_pdf_keys(self, sample_pdf_path):
        result = parse_pdf(sample_pdf_path)
        page = result[0]
        assert "text" in page
        assert "meta" in page
        assert "page" in page["meta"]
        assert "path" in page["meta"]
        assert "doc_id" in page["meta"]

    def test_parse_pdf_doc_id_from_filename(self, sample_pdf_path):
        result = parse_pdf(sample_pdf_path)
        expected_doc_id = os.path.splitext(os.path.basename(sample_pdf_path))[0]
        for page in result:
            assert page["meta"]["doc_id"] == expected_doc_id

    def test_parse_pdf_page_numbers(self, sample_pdf_path):
        result = parse_pdf(sample_pdf_path)
        pages = [p["meta"]["page"] for p in result]
        assert pages == [1, 2]

    def test_parse_pdf_skips_empty_pages(self, sample_pdf_path):
        result = parse_pdf(sample_pdf_path)
        assert len(result) == 2

    def test_parse_pdf_text_content(self, sample_pdf_single_page):
        result = parse_pdf(sample_pdf_single_page)
        assert "Xanthate" in result[0]["text"]

    def test_parse_pdf_path_in_meta(self, sample_pdf_path):
        result = parse_pdf(sample_pdf_path)
        assert result[0]["meta"]["path"] == sample_pdf_path
