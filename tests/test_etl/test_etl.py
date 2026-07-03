from __future__ import annotations

import os
import tempfile
from unittest.mock import MagicMock

import pytest

from hfabric.etl import ETL
from hfabric.schemas import IndexArtifact


@pytest.fixture
def embeddings_provider():
    provider = MagicMock()
    provider.embed.return_value = [[0.1] * 384 for _ in range(10)]
    provider.dim = 384
    return provider


@pytest.fixture
def fake_kg_etl():
    kg = MagicMock()
    return kg


@pytest.fixture
def source_dir_with_pdfs():
    import fitz

    with tempfile.TemporaryDirectory() as tmpdir:
        doc = fitz.open()
        page = doc.new_page()
        page.insert_text((72, 72), "Gold flotation with xanthate collectors at pH 10 achieved 90% recovery.")
        doc.save(os.path.join(tmpdir, "test_doc.pdf"))
        doc.close()
        yield tmpdir


@pytest.fixture
def temp_index_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


class TestETLInit:
    def test_constructor_accepts_dependencies(self, embeddings_provider, fake_kg_etl):
        etl = ETL(embeddings_provider, fake_kg_etl)
        assert etl is not None

    def test_stores_dependencies(self, embeddings_provider, fake_kg_etl):
        etl = ETL(embeddings_provider, fake_kg_etl)
        assert etl._embeddings is embeddings_provider
        assert etl._kg is fake_kg_etl


class TestETLBuildIndex:
    def test_returns_index_artifact(
        self, embeddings_provider, fake_kg_etl, source_dir_with_pdfs, temp_index_dir
    ):
        etl = ETL(embeddings_provider, fake_kg_etl)
        result = etl.build_index(source_dir_with_pdfs, temp_index_dir, "session-1", "pdf")
        assert isinstance(result, IndexArtifact)

    def test_index_artifact_fields(
        self, embeddings_provider, fake_kg_etl, source_dir_with_pdfs, temp_index_dir
    ):
        etl = ETL(embeddings_provider, fake_kg_etl)
        result = etl.build_index(source_dir_with_pdfs, temp_index_dir, "session-1", "pdf")
        assert result.index_dir == temp_index_dir
        assert result.faiss_path == os.path.join(temp_index_dir, "faiss.bin")
        assert result.source == source_dir_with_pdfs
        assert result.session_id == "session-1"
        assert result.num_chunks > 0

    def test_creates_faiss_index(
        self, embeddings_provider, fake_kg_etl, source_dir_with_pdfs, temp_index_dir
    ):
        etl = ETL(embeddings_provider, fake_kg_etl)
        etl.build_index(source_dir_with_pdfs, temp_index_dir, None, "pdf")
        assert os.path.isfile(os.path.join(temp_index_dir, "faiss.bin"))

    def test_creates_chunks_json(
        self, embeddings_provider, fake_kg_etl, source_dir_with_pdfs, temp_index_dir
    ):
        etl = ETL(embeddings_provider, fake_kg_etl)
        etl.build_index(source_dir_with_pdfs, temp_index_dir, None, "pdf")
        assert os.path.isfile(os.path.join(temp_index_dir, "chunks.json"))

    def test_calls_embeddings_provider(
        self, embeddings_provider, fake_kg_etl, source_dir_with_pdfs, temp_index_dir
    ):
        etl = ETL(embeddings_provider, fake_kg_etl)
        etl.build_index(source_dir_with_pdfs, temp_index_dir, None, "pdf")
        embeddings_provider.embed.assert_called()

    def test_calls_kg_add_entities(
        self, embeddings_provider, fake_kg_etl, source_dir_with_pdfs, temp_index_dir
    ):
        etl = ETL(embeddings_provider, fake_kg_etl)
        etl.build_index(source_dir_with_pdfs, temp_index_dir, "sess-1", "pdf")
        fake_kg_etl.add_entities.assert_called()

    def test_calls_kg_add_edges(
        self, embeddings_provider, fake_kg_etl, source_dir_with_pdfs, temp_index_dir
    ):
        etl = ETL(embeddings_provider, fake_kg_etl)
        etl.build_index(source_dir_with_pdfs, temp_index_dir, "sess-1", "pdf")
        fake_kg_etl.add_edges.assert_called()

    def test_embeddings_called_with_passage_prefix(
        self, embeddings_provider, fake_kg_etl, source_dir_with_pdfs, temp_index_dir
    ):
        etl = ETL(embeddings_provider, fake_kg_etl)
        etl.build_index(source_dir_with_pdfs, temp_index_dir, None, "pdf")
        call_kwargs = embeddings_provider.embed.call_args
        assert call_kwargs is not None
        kwargs = call_kwargs[1] if len(call_kwargs) > 1 else {}
        assert kwargs.get("prefix", "") == "passage: "

    def test_idempotency_no_rebuild(
        self, embeddings_provider, fake_kg_etl, source_dir_with_pdfs, temp_index_dir
    ):
        etl = ETL(embeddings_provider, fake_kg_etl)
        etl.build_index(source_dir_with_pdfs, temp_index_dir, None, "pdf")

        embeddings_provider.reset_mock()
        fake_kg_etl.reset_mock()

        result = etl.build_index(source_dir_with_pdfs, temp_index_dir, None, "pdf")
        embeddings_provider.embed.assert_not_called()
        fake_kg_etl.add_entities.assert_not_called()
        fake_kg_etl.add_edges.assert_not_called()
        assert isinstance(result, IndexArtifact)
        assert result.num_chunks > 0

    def test_session_id_passed_through(
        self, embeddings_provider, fake_kg_etl, source_dir_with_pdfs, temp_index_dir
    ):
        etl = ETL(embeddings_provider, fake_kg_etl)
        result = etl.build_index(source_dir_with_pdfs, temp_index_dir, "my-session", "pdf")
        assert result.session_id == "my-session"

    def test_source_kind_passed_to_kg(
        self, embeddings_provider, fake_kg_etl, source_dir_with_pdfs, temp_index_dir
    ):
        etl = ETL(embeddings_provider, fake_kg_etl)
        etl.build_index(source_dir_with_pdfs, temp_index_dir, "sess", "pdf_source")
        call_args = fake_kg_etl.add_entities.call_args
        assert call_args[0][2] == "pdf_source"
