"""Tests for the DefiLlama API client — uses mocks to avoid network calls."""

import pytest
from unittest.mock import patch, MagicMock
from data.defillama import (
    fetch_risk_free_rate,
    fetch_aave_opportunities,
    _normalize_pool,
)
from models.opportunity import Opportunity


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

SAMPLE_POOLS = [
    {
        "pool": "aaaa-bbbb-cccc-dddd-aave3-usdc-polygon",
        "project": "aave-v3",
        "chain": "Polygon",
        "symbol": "USDC",
        "tvlUsd": 180_000_000,
        "apy": 3.85,
        "apyBase": 3.85,
        "apyReward": 0.0,
        "rewardTokens": [],
        "rewardTokenSymbols": [],
        "poolMeta": "USDC Aave V3 Polygon",
        "underlyingTokens": ["0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174"],
        "ilRisk": "no",
        "exposure": "single",
        "predictions": {},
    },
    {
        "pool": "bbbb-cccc-dddd-eeee-aave3-usdt-polygon",
        "project": "aave-v3",
        "chain": "Polygon",
        "symbol": "USDT",
        "tvlUsd": 90_000_000,
        "apy": 4.10,
        "apyBase": 3.50,
        "apyReward": 0.60,
        "rewardTokens": ["0xrewardtoken"],
        "rewardTokenSymbols": ["MATIC"],
        "poolMeta": "USDT Aave V3 Polygon",
        "underlyingTokens": [],
        "ilRisk": "no",
        "exposure": "single",
        "predictions": {},
    },
    {
        "pool": "cccc-dddd-eeee-ffff-aave3-usdc-ethereum",
        "project": "aave-v3",
        "chain": "Ethereum",
        "symbol": "USDC",
        "tvlUsd": 500_000_000,
        "apy": 3.95,
        "apyBase": 3.95,
        "apyReward": 0.0,
        "rewardTokens": [],
        "rewardTokenSymbols": [],
        "poolMeta": "USDC Aave V3 Ethereum",
        "underlyingTokens": [],
        "ilRisk": "no",
        "exposure": "single",
        "predictions": {},
    },
    # Non-stablecoin — should be excluded
    {
        "pool": "dddd-eeee-ffff-gggg-aave3-weth-ethereum",
        "project": "aave-v3",
        "chain": "Ethereum",
        "symbol": "WETH",
        "tvlUsd": 300_000_000,
        "apy": 2.0,
        "apyBase": 2.0,
        "apyReward": 0.0,
        "rewardTokens": [],
        "rewardTokenSymbols": [],
        "poolMeta": None,
        "underlyingTokens": [],
        "ilRisk": "no",
        "exposure": "single",
        "predictions": {},
    },
    # Below TVL threshold — should be excluded
    {
        "pool": "eeee-ffff-gggg-hhhh-aave3-dai-polygon",
        "project": "aave-v3",
        "chain": "Polygon",
        "symbol": "DAI",
        "tvlUsd": 50_000,   # < $100k threshold
        "apy": 5.0,
        "apyBase": 5.0,
        "apyReward": 0.0,
        "rewardTokens": [],
        "rewardTokenSymbols": [],
        "poolMeta": None,
        "underlyingTokens": [],
        "ilRisk": "no",
        "exposure": "single",
        "predictions": {},
    },
]


def mock_pools_response():
    return {"data": SAMPLE_POOLS}


# ──────────────────────────────────────────────
# fetch_risk_free_rate
# ──────────────────────────────────────────────

class TestFetchRiskFreeRate:
    def test_returns_rate_from_aave_ethereum(self):
        with patch("data.defillama._get", return_value=mock_pools_response()):
            rate = fetch_risk_free_rate()
        # USDC Aave V3 Ethereum = 3.95% → 0.0395
        assert rate == pytest.approx(0.0395)

    def test_fallback_on_error(self):
        with patch("data.defillama._get", side_effect=Exception("network error")):
            rate = fetch_risk_free_rate()
        assert rate == 0.04

    def test_fallback_when_no_matching_pool(self):
        with patch("data.defillama._get", return_value={"data": []}):
            rate = fetch_risk_free_rate()
        assert rate == 0.04


# ──────────────────────────────────────────────
# _normalize_pool
# ──────────────────────────────────────────────

class TestNormalizePool:
    def test_returns_opportunity(self):
        pool = SAMPLE_POOLS[0]
        opp = _normalize_pool(pool, risk_free_rate=0.04)
        assert isinstance(opp, Opportunity)

    def test_apy_converted_from_pct(self):
        pool = SAMPLE_POOLS[0]  # apy = 3.85 (percent)
        opp = _normalize_pool(pool, risk_free_rate=0.04)
        assert opp.apy == pytest.approx(0.0385)

    def test_reward_mix_populated(self):
        pool = SAMPLE_POOLS[1]  # has reward tokens
        opp = _normalize_pool(pool, risk_free_rate=0.04)
        assert opp.reward_mix.reward_apy == pytest.approx(0.006)
        assert "MATIC" in opp.reward_mix.reward_tokens

    def test_below_tvl_threshold_returns_none(self):
        pool = SAMPLE_POOLS[4]  # $50k TVL
        assert _normalize_pool(pool, risk_free_rate=0.04) is None

    def test_url_contains_pool_id(self):
        pool = SAMPLE_POOLS[0]
        opp = _normalize_pool(pool, risk_free_rate=0.04)
        assert pool["pool"][:8] in opp.url or pool["pool"] in opp.url

    def test_source_is_defillama(self):
        pool = SAMPLE_POOLS[0]
        opp = _normalize_pool(pool, risk_free_rate=0.04)
        assert opp.source == "defillama"

    def test_chain_display_name(self):
        pool = SAMPLE_POOLS[0]  # chain: "Polygon"
        opp = _normalize_pool(pool, risk_free_rate=0.04)
        assert opp.chain == "Polygon"


# ──────────────────────────────────────────────
# fetch_aave_opportunities
# ──────────────────────────────────────────────

class TestFetchAaveOpportunities:
    def test_returns_list_of_opportunities(self):
        with patch("data.defillama._get", return_value=mock_pools_response()):
            opps = fetch_aave_opportunities(risk_free_rate=0.04)
        assert isinstance(opps, list)
        assert all(isinstance(o, Opportunity) for o in opps)

    def test_excludes_non_stablecoins(self):
        with patch("data.defillama._get", return_value=mock_pools_response()):
            opps = fetch_aave_opportunities(risk_free_rate=0.04)
        symbols = {o.asset for o in opps}
        assert "WETH" not in symbols

    def test_excludes_low_tvl(self):
        with patch("data.defillama._get", return_value=mock_pools_response()):
            opps = fetch_aave_opportunities(risk_free_rate=0.04)
        # The $50k DAI pool should be excluded
        assert all(o.tvl_usd >= 100_000 for o in opps)

    def test_sorted_by_score_descending(self):
        with patch("data.defillama._get", return_value=mock_pools_response()):
            opps = fetch_aave_opportunities(risk_free_rate=0.04)
        scores = [o.score for o in opps]
        assert scores == sorted(scores, reverse=True)

    def test_chain_filter(self):
        with patch("data.defillama._get", return_value=mock_pools_response()):
            opps = fetch_aave_opportunities(chains=["Polygon"], risk_free_rate=0.04)
        assert all(o.chain == "Polygon" for o in opps)

    def test_chain_filter_ethereum(self):
        with patch("data.defillama._get", return_value=mock_pools_response()):
            opps = fetch_aave_opportunities(chains=["Ethereum"], risk_free_rate=0.04)
        assert all(o.chain == "Ethereum" for o in opps)
        assert len(opps) >= 1

    def test_all_have_reward_mix(self):
        with patch("data.defillama._get", return_value=mock_pools_response()):
            opps = fetch_aave_opportunities(risk_free_rate=0.04)
        for o in opps:
            assert o.reward_mix is not None

    def test_all_have_source_confidence(self):
        with patch("data.defillama._get", return_value=mock_pools_response()):
            opps = fetch_aave_opportunities(risk_free_rate=0.04)
        for o in opps:
            assert o.source_confidence in {"high", "medium", "low"}
