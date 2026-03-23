"""Tests for the Kamino API client — uses mocks to avoid network calls."""

import pytest
from unittest.mock import patch

from data.kamino import (
    fetch_kamino_opportunities,
    _build_vault_tvl,
    _fetch_vault_metrics,
)
from models.opportunity import Opportunity


# ──────────────────────────────────────────────
# Test data
# ──────────────────────────────────────────────

SAMPLE_VAULT = {
    "address": "HDsayqAsDWy3QvANGqh2yNraqcD8Fnjgh73Mhb3WRS5E",
    "state": {
        "tokenMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "name": "Steakhouse USDC",
        "vaultFarm": "9FVjHqduhD8ZbXhZLGHbK4S3VQUQBtJbC1SG6Y36VZK3",
        "prevAum": "63148863425446.0",
        "tokenMintDecimals": "6",
    },
}

SAMPLE_METRICS = {
    "apy": "0.0395",
    "apy7d": "0.0380",
    "apy30d": "0.0390",
    "apy90d": "0.0420",
    "apy365d": "0.0580",
    "apyTheoretical": "0.0300",
    "apyActual": "0.0350",
    "apyFarmRewards": "0.0045",
    "apyIncentives": "0.0",
    "apyReservesIncentives": "0.0",
    "tokensInvested": "63148863.425536374346",
    "tokensInvestedUsd": "63146310.31698807991",
    "tokensAvailable": "49362.958848",
    "tokensAvailableUsd": "49360.96310357377536",
    "sharePrice": "1.0377771088980838549",
    "numberOfHolders": 3907,
}

LOW_TVL_METRICS = {
    "apy": "0.05",
    "apyActual": "0.05",
    "apyTheoretical": "0.05",
    "apyFarmRewards": "0",
    "apyIncentives": "0",
    "apyReservesIncentives": "0",
    "tokensInvestedUsd": "50000",   # < $100k MIN_TVL_USD
}

NON_USDC_VAULT = {
    "address": "NonUSDCVault11111111111111111111111",
    "state": {
        "tokenMint": "OtherTokenMintXXXXXXXXXXXXXXXXXXXXX",
        "name": "SOL Vault",
        "vaultFarm": "9FVjHqduhD8ZbXhZLGHbK4S3VQUQBtJbC1SG6Y36VZK3",
    },
}

INACTIVE_VAULT = {
    "address": "InactiveVault1111111111111111111111111",
    "state": {
        "tokenMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
        "name": "Inactive USDC Vault",
        "vaultFarm": "11111111111111111111111111111111",
    },
}


# ──────────────────────────────────────────────
# _build_vault_tvl
# ──────────────────────────────────────────────

class TestBuildVaultTvl:
    def test_returns_prev_aum(self):
        state = {"prevAum": "1234567.89"}
        assert _build_vault_tvl(state) == 1234567.89

    def test_returns_zero_for_missing(self):
        assert _build_vault_tvl({}) == 0.0


# ──────────────────────────────────────────────
# _fetch_vault_metrics — test the public interface
# ──────────────────────────────────────────────

class TestFetchVaultMetrics:
    def test_returns_metrics_dict_on_success(self):
        with patch("data.kamino._get", return_value=SAMPLE_METRICS):
            result = _fetch_vault_metrics("some-address")
        assert result == SAMPLE_METRICS

    def test_returns_none_on_error(self):
        with patch("data.kamino._get", side_effect=Exception("network error")):
            result = _fetch_vault_metrics("some-address")
        assert result is None


# ──────────────────────────────────────────────
# fetch_kamino_opportunities — end-to-end with mocked _fetch_vault_metrics
# ──────────────────────────────────────────────

class TestFetchKaminoOpportunities:
    def test_returns_list_of_opportunities(self):
        """Full pipeline: vault list → per-vault metrics → normalized opps."""
        with patch("data.kamino._get") as mock_get:
            mock_get.return_value = [SAMPLE_VAULT]          # vaults list
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        assert isinstance(opps, list)
        assert all(isinstance(o, Opportunity) for o in opps)

    def test_apy_converted_from_decimal(self):
        """Kamino metrics.apy is decimal: '0.0395' = 3.95%."""
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        assert len(opps) == 1
        assert opps[0].apy == pytest.approx(0.0395)
        assert opps[0].apy_pct == pytest.approx(3.95)

    def test_apy_base_from_actual(self):
        """apyActual is used as the organic base APY."""
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        assert opps[0].reward_mix.base_apy == pytest.approx(0.0350)

    def test_apy_reward_from_farm_incentives(self):
        """apyFarmRewards + apyIncentives + apyReservesIncentives = reward APY."""
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        # apyFarmRewards=0.0045, apyIncentives=0, apyReservesIncentives=0
        assert opps[0].reward_mix.reward_apy == pytest.approx(0.0045)

    def test_min_tvl_filter_excludes_low_tvl(self):
        """Vault with tokensInvestedUsd < $100k is excluded."""
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=LOW_TVL_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        assert opps == []

    def test_non_usdc_excluded(self):
        with patch("data.kamino._get", return_value=[NON_USDC_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        assert opps == []

    def test_inactive_vault_excluded(self):
        with patch("data.kamino._get", return_value=[INACTIVE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        assert opps == []

    def test_solana_chain(self):
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        assert all(o.chain == "Solana" for o in opps)

    def test_opportunity_type_lending(self):
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        assert all(o.to_dict()["opportunity_type"] == "LENDING" for o in opps)

    def test_protocol_and_display(self):
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        assert opps[0].protocol == "kamino"
        assert opps[0].protocol_display == "Kamino"

    def test_pool_url_format(self):
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        addr = SAMPLE_VAULT["address"]
        assert addr in opps[0].url

    def test_source_confidence_medium(self):
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        assert opps[0].source_confidence == "medium"

    def test_withdrawal_constraints_epoch_based(self):
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        assert opps[0].to_dict()["withdrawal_constraints"] == "Epoch-based"

    def test_liquidity_profile_interval(self):
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        assert opps[0].to_dict()["liquidity_profile"] == "INTERVAL"

    def test_curator_is_kamino_team(self):
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        assert opps[0].to_dict()["curator_or_strategy_manager"] == "Kamino Team"

    def test_extra_contains_kamino_fields(self):
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        extra = opps[0].extra
        assert extra["vault_name"] == "Steakhouse USDC"
        assert extra["apyFarmRewards"] == "0.0045"
        assert extra["apy30d"] == "0.0390"

    def test_graceful_fallback_on_api_failure(self):
        """If vault list API fails, return empty list."""
        with patch("data.kamino._get", side_effect=Exception("network error")):
            opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        assert opps == []

    def test_graceful_fallback_on_metrics_failure(self):
        """If vault list succeeds but metrics call fails, skip that vault."""
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=None):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        assert opps == []

    def test_sorted_by_score_descending(self):
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        scores = [o.score for o in opps]
        assert scores == sorted(scores, reverse=True)

    def test_all_have_reward_mix(self):
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        for o in opps:
            assert o.reward_mix is not None

    def test_source_is_kamino_api(self):
        with patch("data.kamino._get", return_value=[SAMPLE_VAULT]):
            with patch("data.kamino._fetch_vault_metrics", return_value=SAMPLE_METRICS):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)
        assert all(o.source == "kamino_api" for o in opps)
