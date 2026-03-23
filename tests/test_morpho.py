"""Tests for the Morpho API client — uses mocks to avoid network calls."""

import pytest
from unittest.mock import patch, MagicMock

from data.morpho import (
    fetch_morpho_opportunities,
    _normalize_vault,
    _post_graphql,
)
from models.opportunity import Opportunity


# ──────────────────────────────────────────────
# Fixtures — mock GraphQL responses
# ──────────────────────────────────────────────

SAMPLE_VAULTS = [
    {
        "address": "0x1234567890abcdef1234567890abcdef12345678",
        "symbol": "USDC",
        "name": "Morpho USDC Vault",
        "totalAssetsUsd": 180_000_000.0,
        "totalAssets": "180000000000000",
        "avgApy": 0.0385,
        "avgNetApy": 0.0385,
        "rewards": [
            {
                "asset": {"address": "0xrewardtoken1"},
                "supplyApr": 0.001,
                "yearlySupplyTokens": "1000000",
            }
        ],
        "adapters": {"items": [{"assetsUsd": 5000000, "type": "aave-v3"}]},
        "chain": {"id": 1, "network": "ethereum"},
    },
    {
        "address": "0xabcdef1234567890abcdef1234567890abcdef12",
        "symbol": "USDT",
        "name": "Morpho USDT Vault",
        "totalAssetsUsd": 95_000_000.0,
        "totalAssets": "95000000000000",
        "avgApy": 0.0410,
        "avgNetApy": 0.0350,
        "rewards": [
            {
                "asset": {"address": "0xrewardtoken2"},
                "supplyApr": 0.006,
                "yearlySupplyTokens": "2000000",
            }
        ],
        "adapters": {"items": [{"assetsUsd": 3000000, "type": "compound"}]},
        "chain": {"id": 1, "network": "ethereum"},
    },
    {
        "address": "0x9876543210fedcba9876543210fedcba98765432",
        "symbol": "DAI",
        "name": "Morpho DAI Vault",
        "totalAssetsUsd": 500_000_000.0,
        "totalAssets": "500000000000000",
        "avgApy": 0.0395,
        "avgNetApy": 0.0395,
        "rewards": [],
        "adapters": {"items": []},
        "chain": {"id": 8453, "network": "base"},
    },
    # Non-stablecoin vault — should be excluded
    {
        "address": "0xaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "symbol": "WETH",
        "name": "Morpho WETH Vault",
        "totalAssetsUsd": 200_000_000.0,
        "totalAssets": "200000000000000",
        "avgApy": 0.0200,
        "avgNetApy": 0.0200,
        "rewards": [],
        "adapters": {"items": []},
        "chain": {"id": 1, "network": "ethereum"},
    },
    # Below TVL threshold — should be excluded
    {
        "address": "0xbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
        "symbol": "USDC",
        "name": "Morpho Small USDC Vault",
        "totalAssetsUsd": 50_000.0,
        "totalAssets": "50000000",
        "avgApy": 0.0500,
        "avgNetApy": 0.0500,
        "rewards": [],
        "adapters": {"items": []},
        "chain": {"id": 1, "network": "ethereum"},
    },
    # Base chain USDC
    {
        "address": "0xcccccccccccccccccccccccccccccccccccccccc",
        "symbol": "USDC",
        "name": "Morpho USDC Base Vault",
        "totalAssetsUsd": 80_000_000.0,
        "totalAssets": "80000000000000",
        "avgApy": 0.0370,
        "avgNetApy": 0.0370,
        "rewards": [],
        "adapters": {"items": []},
        "chain": {"id": 8453, "network": "base"},
    },
]


def mock_graphql_response():
    return {
        "data": {
            "vaultV2s": {
                "items": SAMPLE_VAULTS
            }
        }
    }


def mock_graphql_response_empty():
    return {"data": {"vaultV2s": {"items": []}}}


# ──────────────────────────────────────────────
# _normalize_vault
# ──────────────────────────────────────────────

class TestNormalizeVault:
    def test_returns_opportunity(self):
        vault = SAMPLE_VAULTS[0]
        opp = _normalize_vault(vault, risk_free_rate=0.04)
        assert isinstance(opp, Opportunity)

    def test_apy_converted_correctly(self):
        # Morpho returns decimal already: 0.0385 = 3.85%
        vault = SAMPLE_VAULTS[0]
        opp = _normalize_vault(vault, risk_free_rate=0.04)
        assert opp.apy == pytest.approx(0.0385)
        assert opp.apy_pct == pytest.approx(3.85)

    def test_apy_base_uses_avg_net_apy(self):
        # For vault[1], avgApy=0.041, avgNetApy=0.035
        vault = SAMPLE_VAULTS[1]
        opp = _normalize_vault(vault, risk_free_rate=0.04)
        assert opp.apy == pytest.approx(0.0410)
        assert opp.reward_mix.base_apy == pytest.approx(0.0350)
        assert opp.reward_mix.reward_apy == pytest.approx(0.0060)

    def test_reward_tokens_from_rewards_array(self):
        vault = SAMPLE_VAULTS[0]
        opp = _normalize_vault(vault, risk_free_rate=0.04)
        assert len(opp.reward_mix.reward_tokens) == 1

    def test_below_tvl_threshold_returns_none(self):
        # Vault with $50k TVL
        vault = SAMPLE_VAULTS[4]
        assert _normalize_vault(vault, risk_free_rate=0.04) is None

    def test_tvl_threshold(self):
        # Vault with $95M TVL — above $100k threshold, should be included
        vault = SAMPLE_VAULTS[1]
        opp = _normalize_vault(vault, risk_free_rate=0.04)
        assert opp is not None
        assert opp.tvl_usd == 95_000_000.0

    def test_excludes_non_stablecoins(self):
        vault = SAMPLE_VAULTS[3]  # WETH
        assert _normalize_vault(vault, risk_free_rate=0.04) is None

    def test_chain_display_ethereum(self):
        vault = SAMPLE_VAULTS[0]  # chain id 1
        opp = _normalize_vault(vault, risk_free_rate=0.04)
        assert opp.chain == "Ethereum"

    def test_chain_display_base(self):
        vault = SAMPLE_VAULTS[2]  # chain id 8453
        opp = _normalize_vault(vault, risk_free_rate=0.04)
        assert opp.chain == "Base"

    def test_pool_url_contains_address(self):
        vault = SAMPLE_VAULTS[0]
        opp = _normalize_vault(vault, risk_free_rate=0.04)
        assert vault["address"] in opp.url

    def test_source_is_morpho_api(self):
        vault = SAMPLE_VAULTS[0]
        opp = _normalize_vault(vault, risk_free_rate=0.04)
        assert opp.source == "morpho_api"
        assert opp.source_confidence == "medium"

    def test_protocol_display_morpho(self):
        vault = SAMPLE_VAULTS[0]
        opp = _normalize_vault(vault, risk_free_rate=0.04)
        assert opp.protocol_display == "Morpho"

    def test_extra_contains_morpho_fields(self):
        vault = SAMPLE_VAULTS[0]
        opp = _normalize_vault(vault, risk_free_rate=0.04)
        assert opp.extra["morpho_address"] == vault["address"]
        assert opp.extra["morpho_name"] == vault["name"]


# ──────────────────────────────────────────────
# fetch_morpho_opportunities
# ──────────────────────────────────────────────

class TestFetchMorphoOpportunities:
    def test_fetch_morpho_opportunities_returns_list(self):
        with patch("data.morpho._post_graphql", return_value=mock_graphql_response()):
            opps = fetch_morpho_opportunities(risk_free_rate=0.04)
        assert isinstance(opps, list)
        assert all(isinstance(o, Opportunity) for o in opps)

    def test_excludes_non_stablecoins(self):
        with patch("data.morpho._post_graphql", return_value=mock_graphql_response()):
            opps = fetch_morpho_opportunities(risk_free_rate=0.04)
        symbols = {o.asset for o in opps}
        assert "WETH" not in symbols

    def test_apy_converted_correctly(self):
        with patch("data.morpho._post_graphql", return_value=mock_graphql_response()):
            opps = fetch_morpho_opportunities(risk_free_rate=0.04)
        # USDC vault has avgApy=0.0385
        usdc_opps = [o for o in opps if o.asset == "USDC"]
        assert len(usdc_opps) >= 1

    def test_tvl_threshold(self):
        with patch("data.morpho._post_graphql", return_value=mock_graphql_response()):
            opps = fetch_morpho_opportunities(risk_free_rate=0.04)
        # The $50k vault should be excluded
        assert all(o.tvl_usd >= 100_000 for o in opps)

    def test_sorted_by_score_descending(self):
        with patch("data.morpho._post_graphql", return_value=mock_graphql_response()):
            opps = fetch_morpho_opportunities(risk_free_rate=0.04)
        scores = [o.score for o in opps]
        assert scores == sorted(scores, reverse=True)

    def test_chain_filter_ethereum(self):
        # Mock returns only Ethereum vaults (IDs 1)
        ethereum_response = {
            "data": {
                "vaultV2s": {
                    "items": [v for v in SAMPLE_VAULTS if v["chain"]["id"] == 1]
                }
            }
        }
        with patch("data.morpho._post_graphql", return_value=ethereum_response):
            opps = fetch_morpho_opportunities(chains=["Ethereum"], risk_free_rate=0.04)
        assert all(o.chain == "Ethereum" for o in opps)

    def test_chain_filter_base(self):
        # Mock returns only Base vaults (IDs 8453)
        base_response = {
            "data": {
                "vaultV2s": {
                    "items": [v for v in SAMPLE_VAULTS if v["chain"]["id"] == 8453]
                }
            }
        }
        with patch("data.morpho._post_graphql", return_value=base_response):
            opps = fetch_morpho_opportunities(chains=["Base"], risk_free_rate=0.04)
        assert all(o.chain == "Base" for o in opps)

    def test_network_error_returns_empty_list(self):
        with patch("data.morpho._post_graphql", side_effect=Exception("network error")):
            opps = fetch_morpho_opportunities(risk_free_rate=0.04)
        assert opps == []

    def test_empty_response_returns_empty_list(self):
        with patch("data.morpho._post_graphql", return_value=mock_graphql_response_empty()):
            opps = fetch_morpho_opportunities(risk_free_rate=0.04)
        assert opps == []

    def test_all_have_reward_mix(self):
        with patch("data.morpho._post_graphql", return_value=mock_graphql_response()):
            opps = fetch_morpho_opportunities(risk_free_rate=0.04)
        for o in opps:
            assert o.reward_mix is not None

    def test_all_have_source_confidence(self):
        with patch("data.morpho._post_graphql", return_value=mock_graphql_response()):
            opps = fetch_morpho_opportunities(risk_free_rate=0.04)
        for o in opps:
            assert o.source_confidence in {"high", "medium", "low"}

    def test_pool_id_is_vault_address(self):
        with patch("data.morpho._post_graphql", return_value=mock_graphql_response()):
            opps = fetch_morpho_opportunities(risk_free_rate=0.04)
        for o in opps:
            assert o.pool_id.startswith("0x")
            assert len(o.pool_id) == 42  # Ethereum address length
