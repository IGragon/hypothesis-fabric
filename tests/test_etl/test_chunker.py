from __future__ import annotations

import pytest

from hfabric.etl.chunker import chunk_document, _token_to_word_count


SAMPLE_TEXT = (
    "Gold flotation is a key process in mineral processing. "
    "It separates valuable minerals from gangue using chemical reagents. "
    "Xanthate collectors are widely used for sulphide mineral flotation.\n\n"
    "Cyanide is often used as a depressant in the flotation of gold ores. "
    "However, cyanide consumption should be minimized for environmental reasons. "
    "Alternative depressants such as sodium metabisulphite have been studied.\n\n"
    "The pH of the pulp significantly affects flotation performance. "
    "Optimal pH ranges from 9 to 11 for most gold flotation circuits. "
    "Lime is commonly used to adjust pH in industrial operations."
)


class TestChunkDocument:
    def test_returns_list_of_dicts(self):
        result = chunk_document("Short text.")
        assert isinstance(result, list)
        assert len(result) > 0
        assert all(isinstance(c, dict) for c in result)

    def test_required_keys(self):
        result = chunk_document("Some sample text for chunking.")
        chunk = result[0]
        assert "text" in chunk
        assert "chunk_id" in chunk
        assert "start" in chunk
        assert "end" in chunk

    def test_chunk_ids_unique(self):
        result = chunk_document(SAMPLE_TEXT)
        ids = [c["chunk_id"] for c in result]
        assert len(ids) == len(set(ids))

    def test_chunk_ids_format(self):
        result = chunk_document("Sample text.")
        assert result[0]["chunk_id"].startswith("chunk_")

    def test_single_chunk_short_text(self):
        result = chunk_document("Short text.", chunk_size=512, overlap=64)
        assert len(result) == 1

    def test_multiple_chunks_long_text(self):
        long_text = "word " * 3000
        result = chunk_document(long_text, chunk_size=100, overlap=20)
        assert len(result) > 1

    def test_chunk_size_approximate_tokens(self):
        result = chunk_document("word " * 1000, chunk_size=100, overlap=20)
        for chunk in result:
            words = chunk["text"].split()
            word_token_approx = len(words) * 1.3
            assert word_token_approx <= 100 + 50

    def test_overlap_between_consecutive_chunks(self):
        result = chunk_document(SAMPLE_TEXT, chunk_size=50, overlap=20)
        if len(result) >= 2:
            c1_words = set(result[0]["text"].split())
            c2_words = set(result[1]["text"].split())
            overlap_words = c1_words & c2_words
            assert len(overlap_words) > 0

    def test_start_end_character_positions(self):
        result = chunk_document("Hello world. This is a test.", chunk_size=10, overlap=2)
        assert result[0]["start"] == 0
        assert result[0]["end"] > 0

    def test_preserves_original_text_in_order(self):
        result = chunk_document(SAMPLE_TEXT, chunk_size=60, overlap=10)
        combined = " ".join(c["text"] for c in result)
        original_words = SAMPLE_TEXT.split()
        first_ten = " ".join(original_words[:10])
        assert first_ten in combined

    def test_default_parameters(self):
        result = chunk_document("Simple text for default testing.")
        assert isinstance(result, list)


class TestTokenToWordCount:
    def test_default_chunk_size(self):
        words = _token_to_word_count(512)
        assert words == int(512 / 1.3)

    def test_default_overlap(self):
        words = _token_to_word_count(64)
        assert words == int(64 / 1.3)

    def test_minimum_one(self):
        assert _token_to_word_count(1) >= 1
