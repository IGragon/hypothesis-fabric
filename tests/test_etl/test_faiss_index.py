from __future__ import annotations

import os
import tempfile

import numpy as np
import pytest

from hfabric.etl.faiss_index import (
    build_faiss,
    get_raw_files_mtime,
    index_exists,
    load_faiss,
)


@pytest.fixture
def temp_index_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def sample_embeddings():
    rng = np.random.RandomState(42)
    vectors = rng.randn(10, 128).astype(np.float32)
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    vectors = vectors / norms
    return vectors.tolist()


@pytest.fixture
def sample_chunks():
    return [
        {
            "chunk_id": f"chunk_{i:04d}",
            "text": f"Sample chunk text number {i}.",
            "meta": {"doc_id": "doc_1", "page": i + 1},
        }
        for i in range(10)
    ]


class TestBuildFaiss:
    def test_returns_faiss_path(self, sample_embeddings, sample_chunks, temp_index_dir):
        result = build_faiss(sample_embeddings, sample_chunks, temp_index_dir)
        assert result == os.path.join(temp_index_dir, "faiss.bin")

    def test_creates_faiss_bin(self, sample_embeddings, sample_chunks, temp_index_dir):
        build_faiss(sample_embeddings, sample_chunks, temp_index_dir)
        assert os.path.isfile(os.path.join(temp_index_dir, "faiss.bin"))

    def test_creates_chunks_json(self, sample_embeddings, sample_chunks, temp_index_dir):
        build_faiss(sample_embeddings, sample_chunks, temp_index_dir)
        assert os.path.isfile(os.path.join(temp_index_dir, "chunks.json"))

    def test_creates_index_dir_if_not_exists(self, sample_embeddings, sample_chunks, temp_index_dir):
        nested = os.path.join(temp_index_dir, "nested", "index")
        build_faiss(sample_embeddings, sample_chunks, nested)
        assert os.path.isdir(nested)

    def test_chunks_json_has_correct_records(self, sample_embeddings, sample_chunks, temp_index_dir):
        build_faiss(sample_embeddings, sample_chunks, temp_index_dir)
        import json
        with open(os.path.join(temp_index_dir, "chunks.json")) as f:
            records = json.load(f)
        assert len(records) == len(sample_chunks)
        assert records[0]["chunk_id"] == "chunk_0000"
        assert records[0]["doc_id"] == "doc_1"
        assert records[0]["text"] == "Sample chunk text number 0."


class TestLoadFaiss:
    def test_load_roundtrip(self, sample_embeddings, sample_chunks, temp_index_dir):
        build_faiss(sample_embeddings, sample_chunks, temp_index_dir)
        index, chunks = load_faiss(temp_index_dir)
        assert index.ntotal == 10
        assert len(chunks) == 10

    def test_index_correct_dimension(self, sample_embeddings, sample_chunks, temp_index_dir):
        build_faiss(sample_embeddings, sample_chunks, temp_index_dir)
        index, _ = load_faiss(temp_index_dir)
        assert index.d == 128

    def test_vectors_normalized_for_cosine(self, sample_embeddings, sample_chunks, temp_index_dir):
        build_faiss(sample_embeddings, sample_chunks, temp_index_dir)
        index, _ = load_faiss(temp_index_dir)

        query = np.array(sample_embeddings[0], dtype=np.float32).reshape(1, -1)
        distances, indices = index.search(query, 1)
        assert 0.99 <= distances[0][0] <= 1.01


class TestIndexExists:
    def test_false_when_no_index(self, temp_index_dir):
        assert index_exists(temp_index_dir) is False

    def test_true_when_index_exists(self, sample_embeddings, sample_chunks, temp_index_dir):
        build_faiss(sample_embeddings, sample_chunks, temp_index_dir)
        assert index_exists(temp_index_dir) is True

    def test_false_for_none(self):
        assert index_exists("") is False

    def test_false_for_nonexistent_dir(self):
        assert index_exists("/nonexistent/path/12345") is False


class TestGetRawFilesMtime:
    def test_returns_zero_for_nonexistent_dir(self):
        assert get_raw_files_mtime("/nonexistent/dir/xyz") == 0.0

    def test_returns_max_mtime(self, temp_index_dir):
        path1 = os.path.join(temp_index_dir, "file1.txt")
        path2 = os.path.join(temp_index_dir, "file2.txt")
        with open(path1, "w") as f:
            f.write("test")
        with open(path2, "w") as f:
            f.write("test")

        mtime = get_raw_files_mtime(temp_index_dir)
        assert mtime > 0.0

    def test_skips_directories(self, temp_index_dir):
        subdir = os.path.join(temp_index_dir, "subdir")
        os.makedirs(subdir, exist_ok=True)
        path1 = os.path.join(temp_index_dir, "file.txt")
        with open(path1, "w") as f:
            f.write("test")

        mtime = get_raw_files_mtime(temp_index_dir)
        assert mtime > 0.0
