"""Tests for the scoring model — all 6 sub-scores and build_opportunity factory."""

import pytest
from models.opportunity import RewardMix
from models.scoring import (
    tvl_score,
    protocol_score,
    chain_score,
    yield_score,
    reward_stability_score,
    confidence_score,
    score_opportunity,
    build_opportunity,
)


# ──────────────────────────────────────────────
# TVL score
# ──────────────────────────────────────────────

class TestTvlScore:
    def test_billion_plus(self):
        assert tvl_score(2_000_000_000) == 10.0

    def test_100m(self):
        assert tvl_score(100_000_000) == 8.0

    def test_50m(self):
        assert tvl_score(50_000_000) == 7.0

    def test_10m(self):
        assert tvl_score(10_000_000) == 5.0

    def test_tiny(self):
        assert tvl_score(500) == 1.0

    def test_zero(self):
        assert tvl_score(0) == 1.0


# ──────────────────────────────────────────────
# Protocol score
# ──────────────────────────────────────────────

class TestProtocolScore:
    def test_aave_v3_perfect(self):
        assert protocol_score("aave-v3") == 10.0

    def test_case_insensitive(self):
        assert protocol_score("AAVE-V3") == 10.0

    def test_morpho(self):
        assert protocol_score("morpho") == 8.0

    def test_unknown_gets_default(self):
        assert protocol_score("some-random-protocol") == 5.0


# ──────────────────────────────────────────────
# Chain score
# ──────────────────────────────────────────────

class TestChainScore:
    def test_ethereum(self):
        assert chain_score("ethereum") == 10.0

    def test_polygon(self):
        assert chain_score("polygon") == 8.0

    def test_case_insensitive(self):
        assert chain_score("Ethereum") == 10.0

    def test_unknown_chain(self):
        assert chain_score("randomchain") == 5.0


# ──────────────────────────────────────────────
# Yield score
# ──────────────────────────────────────────────

class TestYieldScore:
    def test_at_risk_free_low(self):
        # At risk-free rate: low score (not compelling)
        assert yield_score(0.04, 0.04) == 2.0

    def test_below_risk_free(self):
        assert yield_score(0.02, 0.04) == 2.0

    def test_small_excess(self):
        # 0.5pp excess
        assert yield_score(0.045, 0.04) == 4.0

    def test_good_excess(self):
        # 2pp excess
        assert yield_score(0.06, 0.04) == 7.5

    def test_great_excess(self):
        # 2.5pp excess
        assert yield_score(0.065, 0.04) == 9.0

    def test_suspicious_excess(self):
        # >10pp excess — red flag
        assert yield_score(0.20, 0.04) == 3.0


# ──────────────────────────────────────────────
# Reward stability score
# ──────────────────────────────────────────────

class TestRewardStabilityScore:
    def test_all_base(self):
        rm = RewardMix(base_apy=0.04, reward_apy=0.0, reward_tokens=[])
        assert reward_stability_score(rm) == 10.0

    def test_mostly_base(self):
        # ~7.5% reward fraction — clearly in the <= 0.10 bucket
        rm = RewardMix(base_apy=0.037, reward_apy=0.003, reward_tokens=["MATIC"])
        assert reward_stability_score(rm) == 9.5

    def test_half_reward(self):
        # 50% reward
        rm = RewardMix(base_apy=0.025, reward_apy=0.025, reward_tokens=["OP"])
        assert reward_stability_score(rm) == 6.0

    def test_mostly_reward(self):
        # 80% reward
        rm = RewardMix(base_apy=0.01, reward_apy=0.04, reward_tokens=["PENDLE"])
        assert reward_stability_score(rm) == 2.0


# ──────────────────────────────────────────────
# Confidence score
# ──────────────────────────────────────────────

class TestConfidenceScore:
    def test_high(self):
        assert confidence_score("high") == 10.0

    def test_medium(self):
        assert confidence_score("medium") == 7.0

    def test_low(self):
        assert confidence_score("low") == 4.0

    def test_unknown(self):
        assert confidence_score("unknown") == 4.0


# ──────────────────────────────────────────────
# score_opportunity integration
# ──────────────────────────────────────────────

class TestScoreOpportunity:
    def test_returns_score_breakdown(self):
        from models.opportunity import ScoreBreakdown
        rm = RewardMix(base_apy=0.038, reward_apy=0.0, reward_tokens=[])
        result = score_opportunity(
            protocol="aave-v3",
            chain="Polygon",
            apy=0.038,
            tvl_usd=200_000_000,
            reward_mix=rm,
            source_confidence="medium",
            risk_free_rate=0.04,
        )
        assert isinstance(result, ScoreBreakdown)
        assert 0 <= result.composite <= 100

    def test_high_quality_pool_scores_well(self):
        rm = RewardMix(base_apy=0.06, reward_apy=0.0, reward_tokens=[])
        result = score_opportunity(
            protocol="aave-v3",
            chain="Ethereum",
            apy=0.06,
            tvl_usd=500_000_000,
            reward_mix=rm,
            source_confidence="high",
            risk_free_rate=0.04,
        )
        assert result.composite >= 70  # Aave V3 Ethereum big pool should score high

    def test_sketchy_pool_scores_low(self):
        rm = RewardMix(base_apy=0.001, reward_apy=0.50, reward_tokens=["SCAM"])
        result = score_opportunity(
            protocol="unknown-protocol",
            chain="randomchain",
            apy=0.50,
            tvl_usd=50_000,
            reward_mix=rm,
            source_confidence="low",
            risk_free_rate=0.04,
        )
        assert result.composite <= 50


# ──────────────────────────────────────────────
# build_opportunity factory
# ──────────────────────────────────────────────

class TestBuildOpportunity:
    def _build(self, **kwargs):
        defaults = dict(
            pool_id="abcd1234-5678-1234-5678-abcd12345678",
            protocol="aave-v3",
            protocol_display="Aave V3",
            chain="Polygon",
            asset="USDC",
            pool_meta="Aave V3 USDC Polygon",
            apy=0.04,
            apy_base=0.04,
            apy_reward=0.0,
            reward_tokens=[],
            tvl_usd=200_000_000,
            source="defillama",
            source_confidence="medium",
            url="https://defillama.com/yields/pool/abcd1234",
            risk_free_rate=0.04,
        )
        defaults.update(kwargs)
        return build_opportunity(**defaults)

    def test_returns_opportunity(self):
        from models.opportunity import Opportunity
        o = self._build()
        assert isinstance(o, Opportunity)

    def test_id_format(self):
        o = self._build()
        assert o.id.startswith("aave-v3-polygon-usdc-")

    def test_risk_tier_set(self):
        o = self._build()
        assert o.risk_tier in {"low", "medium", "high", "speculative"}

    def test_score_within_range(self):
        o = self._build()
        assert 0 <= o.score <= 100

    def test_to_dict_serializable(self):
        import json
        o = self._build()
        d = o.to_dict()
        # Should not raise
        json.dumps(d)
