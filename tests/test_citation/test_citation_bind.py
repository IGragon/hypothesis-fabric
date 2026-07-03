from __future__ import annotations

import pytest

from hfabric.explain.citation_bind import bind_claims
from hfabric.schemas import EvidenceChunk, Hypothesis


def _chunks_map(chunks):
    return {c.chunk_id: c for c in chunks}


class TestBindClaims:
    def test_exact_match(self, sample_hypotheses, sample_chunks):
        hyp = sample_hypotheses[0:1]
        cmap = _chunks_map(sample_chunks)
        scored, coverage = bind_claims(hyp, cmap, threshold=55.0)

        assert len(scored) == 1
        assert scored[0].score == 0.0
        assert scored[0].features == {}
        assert "chunk_001" in scored[0].cited_refs
        assert coverage == 1.0

    def test_unrelated_claim_not_matched(self, sample_chunks):
        hyp = Hypothesis(
            claim="Quantum entanglement improves froth stability in flotation cells",
            mechanism="Entangled particles reduce surface tension",
            expected_effect="+100% recovery",
            evidence_refs=["chunk_001"],
        )
        cmap = _chunks_map(sample_chunks)
        scored, coverage = bind_claims([hyp], cmap, threshold=55.0)

        assert len(scored) == 1
        assert scored[0].cited_refs == {}
        assert coverage == 0.0

    def test_missing_chunk_id_unmatched(self, sample_hypotheses, sample_chunks):
        hyp = Hypothesis(
            claim="Xanthate collector addition increases Au recovery",
            mechanism="Xanthates chemisorb on gold surfaces",
            expected_effect="+5-10% Au recovery",
            evidence_refs=["chunk_999", "chunk_001"],
        )
        cmap = _chunks_map(sample_chunks)
        scored, coverage = bind_claims([hyp], cmap, threshold=55.0)

        assert "chunk_001" in scored[0].cited_refs
        assert "chunk_999" not in scored[0].cited_refs
        assert coverage == 0.5

    def test_coverage_calculation(self, sample_chunks):
        hypotheses = [
            Hypothesis(
                claim="Xanthate collector addition increases Au recovery",
                mechanism="Xanthates chemisorb on gold surfaces",
                expected_effect="+5-10% Au recovery",
                evidence_refs=["chunk_001", "chunk_002"],
            ),
            Hypothesis(
                claim="Quantum mechanics improves flotation",
                mechanism="Entanglement reduces surface tension",
                expected_effect="+100% recovery",
                evidence_refs=["chunk_003", "chunk_001"],
            ),
        ]
        cmap = _chunks_map(sample_chunks)
        scored, coverage = bind_claims(hypotheses, cmap, threshold=55.0)

        # chunk_001 text is about xanthate collectors → matches H1 claim
        # chunk_002 text is about cyanide → NOT match H1 claim
        # chunk_003 text is about sodium sulphide → NOT match H2 claim
        # chunk_001 text is about xanthate collectors → NOT match H2 claim
        # So matched: chunk_001 for H1 only → 1/4 = 0.25
        assert coverage == 0.25
        assert len(scored) == 2

    def test_empty_evidence_refs(self, sample_chunks):
        hyp = Hypothesis(
            claim="Some claim without evidence",
            mechanism="Unknown mechanism",
            expected_effect="Unknown effect",
            evidence_refs=[],
        )
        cmap = _chunks_map(sample_chunks)
        scored, coverage = bind_claims([hyp], cmap, threshold=55.0)

        assert len(scored) == 1
        assert scored[0].cited_refs == {}
        assert coverage == 0.0

    def test_empty_hypotheses(self):
        scored, coverage = bind_claims([], {}, threshold=55.0)

        assert scored == []
        assert coverage == 0.0

    def test_duplicate_chunk_ids(self, sample_chunks):
        hyp = Hypothesis(
            claim="Sodium sulphide pre-treatment activates oxidized gold",
            mechanism="Sulphidization forms a hydrophobic layer on oxidized gold particles",
            expected_effect="+3-7% Au recovery for oxidized ores",
            evidence_refs=["chunk_003", "chunk_003", "chunk_001"],
        )
        cmap = _chunks_map(sample_chunks)
        scored, coverage = bind_claims([hyp], cmap, threshold=55.0)

        assert scored[0].cited_refs.get("chunk_003") is not None
        assert coverage > 0.0
        assert len(scored[0].cited_refs) <= len(set(hyp.evidence_refs))

    def test_deterministic(self, sample_hypotheses, sample_chunks):
        cmap = _chunks_map(sample_chunks)
        result1 = bind_claims(sample_hypotheses, cmap, threshold=55.0)
        result2 = bind_claims(sample_hypotheses, cmap, threshold=55.0)

        scored1, cov1 = result1
        scored2, cov2 = result2

        assert cov1 == cov2
        for s1, s2 in zip(scored1, scored2):
            assert s1.score == s2.score
            assert s1.features == s2.features
            assert list(s1.cited_refs.keys()) == list(s2.cited_refs.keys())

    def test_short_claim_still_processed(self, sample_chunks):
        hyp = Hypothesis(
            claim="Au",
            mechanism="X",
            expected_effect="Y",
            evidence_refs=["chunk_001"],
        )
        cmap = _chunks_map(sample_chunks)
        scored, coverage = bind_claims([hyp], cmap, threshold=55.0)

        assert len(scored) == 1
        # Very short claim against unrelated text → likely unmatched
        assert isinstance(coverage, float)

    def test_multiple_matches_per_hypothesis(self, sample_chunks):
        hyp = Hypothesis(
            claim="Sodium sulphide and xanthate collectors improve gold recovery",
            mechanism="Combined activation and hydrophobicity",
            expected_effect="+5-15% recovery",
            evidence_refs=["chunk_001", "chunk_003"],
        )
        cmap = _chunks_map(sample_chunks)
        scored, coverage = bind_claims([hyp], cmap, threshold=55.0)

        assert len(scored) == 1
        assert "chunk_003" in scored[0].cited_refs
        assert coverage == 1.0
