from __future__ import annotations

import json
import os

import pytest

from hfabric.session.manager import SessionManager


@pytest.fixture
def manager(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return SessionManager(base_dir=str(tmp_path / "sessions"))


class TestCreateSession:
    def test_returns_unique_session_id_and_creates_dirs(self, manager):
        meta = manager.create_session("increase Au recovery", "no cyanide")
        sid = meta["session_id"]
        assert isinstance(sid, str)
        assert len(sid) == 8
        assert os.path.isdir(manager.raw_files_dir(sid))
        assert os.path.isdir(manager.index_dir(sid))
        assert os.path.isdir(manager.export_dir(sid))

    def test_writes_meta_json(self, manager):
        meta = manager.create_session("query text", "constraints text")
        loaded = manager.get_session(meta["session_id"])
        assert loaded["nl_query"] == "query text"
        assert loaded["constraints"] == "constraints text"
        assert loaded["status"] == "created"
        assert "created_at" in loaded

    def test_session_ids_are_unique(self, manager):
        ids = {manager.create_session("q")["session_id"] for _ in range(20)}
        assert len(ids) == 20


class TestGetSession:
    def test_returns_none_for_unknown(self, manager):
        assert manager.get_session("nonexistent") is None


class TestRawFiles:
    def test_has_raw_files_false_when_empty(self, manager):
        meta = manager.create_session("q")
        assert manager.has_raw_files(meta["session_id"]) is False

    def test_has_raw_files_true_when_supported_file(self, manager):
        meta = manager.create_session("q")
        with open(os.path.join(manager.raw_files_dir(meta["session_id"]), "report.pdf"), "wb") as f:
            f.write(b"%PDF-1.4")
        assert manager.has_raw_files(meta["session_id"]) is True

    def test_has_raw_files_false_when_unsupported(self, manager):
        meta = manager.create_session("q")
        with open(os.path.join(manager.raw_files_dir(meta["session_id"]), "notes.txt"), "w") as f:
            f.write("x")
        assert manager.has_raw_files(meta["session_id"]) is False


class TestUpdateStatus:
    def test_updates_persisted_status(self, manager):
        meta = manager.create_session("q")
        manager.update_status(meta["session_id"], "complete")
        loaded = manager.get_session(meta["session_id"])
        assert loaded["status"] == "complete"

    def test_update_skips_unknown_session(self, manager):
        manager.update_status("nonexistent", "done")


class TestDirHelpers:
    def test_dir_paths_consistent(self, manager):
        meta = manager.create_session("q")
        sid = meta["session_id"]
        assert manager.session_dir(sid).endswith(os.path.join("sessions", sid))
        assert manager.raw_files_dir(sid).endswith(os.path.join(sid, "raw_files"))
        assert manager.index_dir(sid).endswith(os.path.join(sid, "index"))
        assert manager.export_dir(sid).endswith(os.path.join(sid, "export"))


class TestUnicodeSafe:
    def test_cyrillic_query_persisted(self, manager):
        meta = manager.create_session("повысить извлечение Au на 5%", "без цианида")
        loaded = manager.get_session(meta["session_id"])
        assert "извлечение" in loaded["nl_query"]
        assert loaded["constraints"] == "без цианида"