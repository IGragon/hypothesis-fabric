from __future__ import annotations

import json
import os
import sys
from unittest.mock import MagicMock, patch

import pytest

from hfabric.cli import build_arg_parser, cmd_new, cmd_run, cmd_eval, cmd_index_kb
from hfabric.session.manager import SessionManager


class TestSessionManager:
    def test_create_session_creates_dirs(self, tmp_path):
        manager = SessionManager(base_dir=str(tmp_path))
        meta = manager.create_session("test query")

        sid = meta["session_id"]
        assert len(sid) == 8

        assert os.path.isdir(os.path.join(str(tmp_path), sid, "raw_files"))
        assert os.path.isdir(os.path.join(str(tmp_path), sid, "index"))
        assert os.path.isdir(os.path.join(str(tmp_path), sid, "export"))

    def test_create_session_writes_meta(self, tmp_path):
        manager = SessionManager(base_dir=str(tmp_path))
        meta = manager.create_session("increase Au recovery")

        sid = meta["session_id"]
        meta_path = os.path.join(str(tmp_path), sid, "meta.json")
        assert os.path.isfile(meta_path)

        with open(meta_path) as f:
            stored = json.load(f)
        assert stored["session_id"] == sid
        assert stored["nl_query"] == "increase Au recovery"
        assert stored["status"] == "created"
        assert "created_at" in stored

    def test_get_session_returns_meta(self, tmp_path):
        manager = SessionManager(base_dir=str(tmp_path))
        meta = manager.create_session("test query")
        sid = meta["session_id"]

        retrieved = manager.get_session(sid)
        assert retrieved is not None
        assert retrieved["session_id"] == sid
        assert retrieved["nl_query"] == "test query"

    def test_get_session_returns_none_for_nonexistent(self, tmp_path):
        manager = SessionManager(base_dir=str(tmp_path))
        assert manager.get_session("nonexistent") is None

    def test_has_raw_files_false_when_empty(self, tmp_path):
        manager = SessionManager(base_dir=str(tmp_path))
        meta = manager.create_session("test")
        assert manager.has_raw_files(meta["session_id"]) is False

    def test_has_raw_files_true_when_pdf_present(self, tmp_path):
        manager = SessionManager(base_dir=str(tmp_path))
        meta = manager.create_session("test")
        sid = meta["session_id"]
        raw = manager.raw_files_dir(sid)
        with open(os.path.join(raw, "doc.pdf"), "w") as f:
            f.write("fake pdf")
        assert manager.has_raw_files(sid) is True

    def test_update_status(self, tmp_path):
        manager = SessionManager(base_dir=str(tmp_path))
        meta = manager.create_session("test")
        sid = meta["session_id"]

        manager.update_status(sid, "complete")
        updated = manager.get_session(sid)
        assert updated["status"] == "complete"

    def test_update_status_nonexistent_no_error(self, tmp_path):
        manager = SessionManager(base_dir=str(tmp_path))
        manager.update_status("nonexistent", "complete")

    def test_session_dir_methods(self, tmp_path):
        manager = SessionManager(base_dir=str(tmp_path))
        sid = "abc12345"
        assert manager.session_dir(sid) == os.path.join(str(tmp_path), sid)
        assert manager.raw_files_dir(sid) == os.path.join(str(tmp_path), sid, "raw_files")
        assert manager.index_dir(sid) == os.path.join(str(tmp_path), sid, "index")
        assert manager.export_dir(sid) == os.path.join(str(tmp_path), sid, "export")


class TestArgParser:
    def test_index_kb_subcommand(self):
        parser = build_arg_parser()
        args = parser.parse_args(["index-kb"])
        assert args.command == "index-kb"
        assert args.func == cmd_index_kb

    def test_new_subcommand(self):
        parser = build_arg_parser()
        args = parser.parse_args(["new", "test query"])
        assert args.command == "new"
        assert args.query == "test query"
        assert args.func == cmd_new

    def test_run_subcommand(self):
        parser = build_arg_parser()
        args = parser.parse_args(["run", "sess123", "test query"])
        assert args.command == "run"
        assert args.session_id == "sess123"
        assert args.query == "test query"
        assert args.func == cmd_run

    def test_eval_subcommand(self):
        parser = build_arg_parser()
        args = parser.parse_args(["eval", "sess123"])
        assert args.command == "eval"
        assert args.session_id == "sess123"
        assert args.func == cmd_eval

    def test_no_subcommand_errors(self):
        parser = build_arg_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])


class TestCmdNew:
    def test_cmd_new_creates_session(self, tmp_path, capsys):
        with patch("hfabric.session.manager.SessionManager") as MockMgr:
            mock_inst = MockMgr.return_value
            mock_inst.create_session.return_value = {
                "session_id": "abc12345",
                "nl_query": "test query",
                "created_at": "2026-01-01T00:00:00Z",
                "status": "created",
            }

            args = MagicMock()
            args.query = "test query"
            cmd_new(args)

            captured = capsys.readouterr()
            assert "abc12345" in captured.out
            assert "test query" in captured.out
            mock_inst.create_session.assert_called_once_with("test query")


class TestCmdRun:
    def test_cmd_run_nonexistent_session_exits(self, tmp_path, capsys):
        with patch("hfabric.session.manager.SessionManager") as MockMgr:
            mock_inst = MockMgr.return_value
            mock_inst.get_session.return_value = None

            args = MagicMock()
            args.session_id = "nonexistent"
            args.query = "test"

            with pytest.raises(SystemExit):
                cmd_run(args)

    def test_cmd_run_calls_orchestrator(self, tmp_path, capsys):
        mock_state = {
            "status": "complete",
            "explained": [
                {
                    "scored": {
                        "hypothesis": {
                            "claim": "Test hypothesis claim here",
                            "mechanism": "Test mechanism explanation here",
                            "expected_effect": "+5% improvement",
                            "evidence_refs": ["c1"],
                        },
                        "score": 0.85,
                        "features": {"novelty": 0.5, "feasibility": 0.8, "effect": 0.9},
                        "cited_refs": {},
                    },
                    "justification": "Plausible.",
                    "uncertainty": "Low.",
                    "verification_plan": "Test it.",
                    "graph_neighbourhood": ["Material: gold"],
                }
            ],
            "export_json_path": "sessions/test/export/hypotheses.json",
            "export_md_path": "sessions/test/export/report.md",
        }

        with patch("hfabric.session.manager.SessionManager") as MockMgr, \
             patch("hfabric.orchestrator.wiring.build_real_orchestrator") as MockBuild, \
             patch("hfabric.cli._build_session_index") as mock_build_idx:

            mock_inst = MockMgr.return_value
            mock_inst.get_session.return_value = {"session_id": "test", "status": "created"}
            mock_inst.has_raw_files.return_value = False

            mock_orch = MockBuild.return_value
            mock_orch.run.return_value = mock_state

            args = MagicMock()
            args.session_id = "test"
            args.query = "test query"

            cmd_run(args)

            captured = capsys.readouterr()
            assert "Test hypothesis claim here" in captured.out
            assert "0.850" in captured.out
            assert "complete" in captured.out
            mock_orch.run.assert_called_once_with("test", "test query")


class TestCmdEval:
    def test_cmd_eval_nonexistent_session_exits(self, capsys):
        with patch("hfabric.session.manager.SessionManager") as MockMgr:
            mock_inst = MockMgr.return_value
            mock_inst.get_session.return_value = None

            args = MagicMock()
            args.session_id = "nonexistent"

            with pytest.raises(SystemExit):
                cmd_eval(args)

    def test_cmd_eval_no_export_exits(self, capsys):
        with patch("hfabric.session.manager.SessionManager") as MockMgr, \
             patch("hfabric.cli._load_run_result") as mock_load:

            mock_inst = MockMgr.return_value
            mock_inst.get_session.return_value = {"session_id": "test"}
            mock_load.return_value = None

            args = MagicMock()
            args.session_id = "test"

            with pytest.raises(SystemExit):
                cmd_eval(args)

    def test_cmd_eval_runs_evals_and_jaccard(self, capsys):
        result_data = {
            "query": "test query",
            "kpi": {"constraints": ["no cyanide"]},
            "ranked": [
                {
                    "scored": {
                        "hypothesis": {
                            "claim": "Test hypothesis claim here",
                            "mechanism": "Test mechanism explanation",
                            "expected_effect": "+5% recovery",
                            "evidence_refs": ["c1"],
                        },
                        "score": 0.85,
                        "features": {},
                        "cited_refs": {"c1": {"chunk_id": "c1", "doc_id": "d1", "text": "text", "meta": {}}},
                    },
                    "justification": "ok",
                    "uncertainty": "low",
                    "verification_plan": "test",
                    "graph_neighbourhood": [],
                }
            ],
        }

        mock_state = {
            "status": "complete",
            "explained": [
                {
                    "scored": {
                        "hypothesis": {
                            "claim": "Test hypothesis claim here",
                            "mechanism": "Test mechanism explanation",
                            "expected_effect": "+5% recovery",
                            "evidence_refs": ["c1"],
                        },
                        "score": 0.85,
                        "features": {},
                        "cited_refs": {},
                    },
                    "justification": "ok",
                    "uncertainty": "low",
                    "verification_plan": "test",
                    "graph_neighbourhood": [],
                }
            ],
        }

        with patch("hfabric.session.manager.SessionManager") as MockMgr, \
             patch("hfabric.cli._load_run_result", return_value=result_data), \
             patch("hfabric.obs.evals.run_evals") as mock_evals, \
             patch("hfabric.orchestrator.wiring.build_real_orchestrator") as MockBuild, \
             patch("hfabric.obs.evals.jaccard_at_10", return_value=1.0) as mock_jaccard:

            mock_inst = MockMgr.return_value
            mock_inst.get_session.return_value = {"session_id": "test"}
            mock_evals.return_value = {"schema_validity": {"passed": True}}

            mock_orch = MockBuild.return_value
            mock_orch.run.return_value = mock_state

            args = MagicMock()
            args.session_id = "test"

            cmd_eval(args)

            captured = capsys.readouterr()
            assert "Jaccard@10" in captured.out
            assert "1.000" in captured.out
            assert "PASS" in captured.out
            mock_jaccard.assert_called_once()


class TestCmdIndexKb:
    def test_cmd_index_kb_no_kb_dir_exits(self, capsys):
        with patch("os.path.isdir", return_value=False):
            args = MagicMock()
            with pytest.raises(SystemExit):
                cmd_index_kb(args)

    def test_cmd_index_kb_no_pdfs_exits(self, capsys):
        with patch("os.path.isdir", return_value=True), \
             patch("os.listdir", return_value=["readme.txt"]):
            args = MagicMock()
            with pytest.raises(SystemExit):
                cmd_index_kb(args)
