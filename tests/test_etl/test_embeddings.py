from __future__ import annotations

import pytest

from hfabric.embeddings import SentenceTransformersProvider
from hfabric.etl.embeddings import embed_chunks


@pytest.fixture
def sample_chunks():
    return [
        {"text": "Gold flotation is a key process in mineral processing."},
        {"text": "Xanthate collectors improve gold recovery."},
        {"text": "Cyanide is used as a depressant in flotation."},
    ]


class TestEmbedChunks:
    def test_returns_list_of_list_of_floats(self, sample_chunks):
        result = embed_chunks(sample_chunks)
        assert isinstance(result, list)
        assert all(isinstance(v, list) for v in result)
        assert all(isinstance(f, float) for v in result for f in v)

    def test_output_length_matches_input(self, sample_chunks):
        result = embed_chunks(sample_chunks)
        assert len(result) == len(sample_chunks)

    def test_embedding_dimension_matches_model(self, sample_chunks):
        result = embed_chunks(sample_chunks)
        assert len(result[0]) == 384

    def test_different_texts_different_embeddings(self, sample_chunks):
        result = embed_chunks(sample_chunks)
        v1 = result[0]
        v2 = result[1]
        assert v1 != v2

    def test_same_text_same_embedding(self):
        chunks = [{"text": "Gold flotation."}, {"text": "Gold flotation."}]
        result = embed_chunks(chunks)
        assert result[0] == result[1]

    def test_single_chunk(self):
        result = embed_chunks([{"text": "Single chunk."}])
        assert len(result) == 1
        assert len(result[0]) == 384


class TestSentenceTransformersProvider:
    @pytest.fixture
    def provider(self):
        return SentenceTransformersProvider()

    def test_dim_property(self, provider):
        assert provider.dim == 384

    def test_embed_returns_correct_shape(self, provider):
        texts = ["Hello world", "Another sentence"]
        result = provider.embed(texts)
        assert len(result) == 2
        assert len(result[0]) == 384

    def test_embed_with_prefix(self, provider):
        texts = ["query text"]
        result_with = provider.embed(texts, prefix="query: ")
        result_without = provider.embed(texts, prefix="")
        assert len(result_with) == 1
        assert len(result_with[0]) == 384
        assert result_with != result_without

    def test_embed_empty_list(self, provider):
        result = provider.embed([])
        assert result == []

    def test_dim_type(self, provider):
        assert isinstance(provider.dim, int)
