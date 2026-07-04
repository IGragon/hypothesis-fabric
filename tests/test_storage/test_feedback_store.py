from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from hfabric.storage.feedback_store import FeedbackStore


@pytest.fixture
def fb_store():
    db_path = Path(tempfile.gettempdir()) / "test_feedback.db"
    if db_path.exists():
        db_path.unlink()
    store = FeedbackStore(str(db_path))
    yield store
    if db_path.exists():
        db_path.unlink()


class TestFeedbackStore:
    def test_save_and_get_label(self, fb_store):
        fb_store.save_label(
            run_id="run_1",
            hypothesis_claim="Increase Au recovery with PAX",
            label="accepted",
            expert_id="expert_1",
            comment="Looks promising",
        )
        labels = fb_store.get_labels("Increase Au recovery with PAX")
        assert len(labels) == 1
        assert labels[0]["label"] == "accepted"
        assert labels[0]["expert_id"] == "expert_1"
        assert labels[0]["comment"] == "Looks promising"

    def test_get_all_labels(self, fb_store):
        fb_store.save_label("run_1", "claim_A", "accepted", "expert_1")
        fb_store.save_label("run_2", "claim_B", "rejected", "expert_2")
        fb_store.save_label("run_1", "claim_A", "adjusted", "expert_3")
        labels = fb_store.get_all_labels()
        assert len(labels) == 3

    def test_delete_label(self, fb_store):
        lid = fb_store.save_label("run_1", "claim_A", "accepted", "expert_1")
        fb_store.delete_label(lid)
        labels = fb_store.get_all_labels()
        assert len(labels) == 0

    def test_get_label_conflicts(self, fb_store):
        fb_store.save_label("run_1", "claim_X", "accepted", "expert_1")
        fb_store.save_label("run_2", "claim_X", "rejected", "expert_2")
        conflicts = fb_store.get_label_conflicts()
        assert len(conflicts) >= 1
        assert conflicts[0]["hypothesis_claim"] == "claim_X"

    def test_no_conflicts_for_same_label(self, fb_store):
        fb_store.save_label("run_1", "claim_Y", "accepted", "expert_1")
        fb_store.save_label("run_2", "claim_Y", "accepted", "expert_2")
        conflicts = fb_store.get_label_conflicts()
        assert len(conflicts) == 0

    def test_get_labels_returns_empty_for_unknown_claim(self, fb_store):
        labels = fb_store.get_labels("nonexistent claim")
        assert labels == []

    def test_empty_store_all_labels(self, fb_store):
        assert fb_store.get_all_labels() == []
        assert fb_store.get_label_conflicts() == []
