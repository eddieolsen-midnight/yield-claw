"""Tests for the Opportunity schema and RewardMix / ScoreBreakdown."""

import pytest
from models.opportunity import RewardMix, ScoreBreakdown, Opportunity, score_to_risk_tier


# ──────────────────────────────────────────────
# RewardMix
# ──────────────────────────────────────────────

class TestRewardMix:
    def test_total_apy(self):
        rm = RewardMix(base_apy=0.038, reward_apy=0.012, reward_tokens=["MATIC"])
        assert rm.total_apy == pytest.approx(0.05)

    def test_reward_fraction_all_base(self):
        rm = RewardMix(base_apy=0.04, reward_apy=0.0, reward_tokens=[])
        assert rm.reward_fraction == 0.0

    def test_reward_fraction_all_reward(self):
        rm = RewardMix(base_apy=0.0, reward_apy=0.05, reward_tokens=["OP"])
        assert rm.reward_fraction == 1.0

    def test_reward_fraction_mixed(self):
        rm = RewardMix(base_apy=0.03, reward_apy=0.01, reward_tokens=["MATIC"])
        assert rm.reward_fraction == pytest.approx(0.25)

    def test_reward_fraction_zero_total(self):
        rm = RewardMix(base_apy=0.0, reward_apy=0.0, reward_tokens=[])
        assert rm.reward_fraction == 0.0

    def test_to_dict_keys(self):
        rm = RewardMix(base_apy=0.038, reward_apy=0.002, reward_tokens=["MATIC"])
        d = rm.to_dict()
        assert "base_apy" in d
        assert "reward_apy" in d
        assert "reward_tokens" in d
        assert "total_apy" in d
        assert "reward_fraction" in d


# ──────────────────────────────────────────────
# ScoreBreakdown
# ──────────────────────────────────────────────

class TestScoreBreakdown:
    def _perfect(self):
        return ScoreBreakdown(
            tvl_score=10.0,
            protocol_score=10.0,
            chain_score=10.0,
            yield_score=10.0,
            reward_stability_score=10.0,
            confidence_score=10.0,
        )

    def _zero(self):
        return ScoreBreakdown(
            tvl_score=0.0,
            protocol_score=0.0,
            chain_score=0.0,
            yield_score=0.0,
            reward_stability_score=0.0,
            confidence_score=0.0,
        )

    def test_perfect_score_is_100(self):
        assert self._perfect().composite == 100.0

    def test_zero_score_is_0(self):
        assert self._zero().composite == 0.0

    def test_composite_within_range(self):
        sb = ScoreBreakdown(
            tvl_score=7.0,
            protocol_score=9.0,
            chain_score=8.0,
            yield_score=6.0,
            reward_stability_score=8.0,
            confidence_score=7.0,
        )
        assert 0 <= sb.composite <= 100

    def test_weights_sum_to_one(self):
        total = sum(ScoreBreakdown.WEIGHTS.values())
        assert total == pytest.approx(1.0)

    def test_to_dict_has_composite(self):
        d = self._perfect().to_dict()
        assert "composite" in d
        assert d["composite"] == 100.0


# ──────────────────────────────────────────────
# Risk tier
# ──────────────────────────────────────────────

class TestRiskTier:
    def test_low_risk(self):
        assert score_to_risk_tier(80) == "low"

    def test_medium_risk(self):
        assert score_to_risk_tier(60) == "medium"

    def test_high_risk(self):
        assert score_to_risk_tier(40) == "high"

    def test_speculative(self):
        assert score_to_risk_tier(10) == "speculative"

    def test_boundary_75(self):
        assert score_to_risk_tier(75) == "low"

    def test_boundary_50(self):
        assert score_to_risk_tier(50) == "medium"

    def test_boundary_25(self):
        assert score_to_risk_tier(25) == "high"


# ──────────────────────────────────────────────
# Opportunity
# ──────────────────────────────────────────────

def make_opportunity(**overrides):
    defaults = dict(
        id="aave-v3-polygon-usdc-abcd1234",
        protocol="aave-v3",
        protocol_display="Aave V3",
        chain="Polygon",
        asset="USDC",
        pool_id="abcd1234-1234-1234-1234-abcd12345678",
        pool_meta="Aave V3 USDC Polygon",
        apy=0.038,
        reward_mix=RewardMix(base_apy=0.038, reward_apy=0.0, reward_tokens=[]),
        tvl_usd=200_000_000,
        source="defillama",
        source_confidence="medium",
        url="https://defillama.com/yields/pool/abcd1234",
        score_breakdown=ScoreBreakdown(
            tvl_score=8.0,
            protocol_score=10.0,
            chain_score=8.0,
            yield_score=7.5,
            reward_stability_score=10.0,
            confidence_score=7.0,
        ),
        risk_tier="low",
    )
    defaults.update(overrides)
    return Opportunity(**defaults)


class TestOpportunity:
    def test_apy_pct(self):
        o = make_opportunity(apy=0.038)
        assert o.apy_pct == pytest.approx(3.8)

    def test_score_delegates_to_breakdown(self):
        o = make_opportunity()
        assert o.score == o.score_breakdown.composite

    def test_to_dict_required_keys(self):
        o = make_opportunity()
        d = o.to_dict()
        required = [
            "id", "protocol", "chain", "asset", "apy", "apy_pct",
            "reward_mix", "tvl_usd", "source", "source_confidence",
            "score", "score_breakdown", "risk_tier", "fetched_at",
        ]
        for key in required:
            assert key in d, f"Missing key: {key}"

    def test_to_dict_reward_mix_present(self):
        o = make_opportunity()
        d = o.to_dict()
        assert "reward_mix" in d
        assert "base_apy" in d["reward_mix"]
        assert "reward_fraction" in d["reward_mix"]

    def test_to_dict_score_breakdown_present(self):
        o = make_opportunity()
        d = o.to_dict()
        assert "score_breakdown" in d
        assert "composite" in d["score_breakdown"]
        assert "weights" in d["score_breakdown"]
