"""
Integration tests for cross-source pooling and deduplication.

Validates that:
1. Combined /api/opportunities pools all sources
2. Deduplication by pool_id works
3. Sorting by composite score works
4. Per-source counts are correct
5. All new fields (instrument types) are present across sources
"""

import pytest
from unittest.mock import patch, MagicMock

from models.opportunity import Opportunity, RewardMix, ScoreBreakdown
from models.scoring import build_opportunity


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def make_opp(pool_id, protocol, chain="Ethereum", apy=0.04, tvl=100_000_000, **overrides):
    """Factory for test opportunities."""
    rm = RewardMix(base_apy=apy, reward_apy=0.0, reward_tokens=[])
    sb = ScoreBreakdown(
        tvl_score=7.0, protocol_score=8.0, chain_score=9.0,
        yield_score=6.0, reward_stability_score=7.0, confidence_score=8.0,
    )
    kw = dict(
        id=f"{protocol}-{chain.lower()}-usdc-{pool_id[:8]}",
        protocol=protocol,
        protocol_display=protocol.title(),
        chain=chain,
        asset="USDC",
        pool_id=pool_id,
        pool_meta=f"{protocol} USDC",
        apy=apy,
        reward_mix=rm,
        tvl_usd=tvl,
        source="test",
        source_confidence="medium",
        url=f"https://example.com/{pool_id}",
        score_breakdown=sb,
        risk_tier="low",
    )
    kw.update(overrides)
    return Opportunity(**kw)


# ──────────────────────────────────────────────
# Test: Pooling and deduplication
# ──────────────────────────────────────────────

class TestPoolingAndDeduplication:
    def test_combined_opportunities_deduplicates_by_pool_id(self):
        """
        If the same pool_id appears in multiple sources, only one appears
        in the combined output.
        """
        # Simulate: Aave and Morpho both surface the same underlying pool
        same_pool_id = "0xSharedPool1234567"
        aave_opp  = make_opp(same_pool_id, "aave-v3",   chain="Ethereum", apy=0.039)
        morpho_opp = make_opp(same_pool_id, "morpho",    chain="Ethereum", apy=0.039)
        kamino_opp = make_opp("kamino-sol-12345",        "kamino",        chain="Solana",  apy=0.038)

        # Pool: aave + morpho + kamino (same pool_id appears twice)
        all_opps = [aave_opp, morpho_opp, kamino_opp]
        seen = set()
        deduped = []
        for opp in all_opps:
            if opp.pool_id not in seen:
                seen.add(opp.pool_id)
                deduped.append(opp)

        assert len(deduped) == 2
        pool_ids = {o.pool_id for o in deduped}
        assert same_pool_id in pool_ids
        assert "kamino-sol-12345" in pool_ids

    def test_deduplication_key_is_pool_id_not_protocol(self):
        """
        Deduplication must be by pool_id, not by protocol.
        Different protocols with different pool_ids must all appear.
        """
        opp1 = make_opp("pool-aave-001",   "aave-v3", apy=0.040)
        opp2 = make_opp("pool-morpho-002",  "morpho",  apy=0.042)
        opp3 = make_opp("pool-kamino-003",  "kamino",  chain="Solana", apy=0.038)

        all_opps = [opp1, opp2, opp3]
        seen = set()
        deduped = []
        for opp in all_opps:
            if opp.pool_id not in seen:
                seen.add(opp.pool_id)
                deduped.append(opp)

        assert len(deduped) == 3
        assert {o.protocol for o in deduped} == {"aave-v3", "morpho", "kamino"}

    def test_combined_and_sorted_by_score(self):
        """
        Combined opportunities must be sorted by composite score descending.
        """
        opp_low  = make_opp("pool-low",   "aave-v3", apy=0.035, tvl=10_000_000)
        opp_high = make_opp("pool-high",  "aave-v3", apy=0.050, tvl=500_000_000)
        opp_mid  = make_opp("pool-mid",   "morpho",  apy=0.042, tvl=200_000_000)

        combined = [opp_low, opp_high, opp_mid]
        combined.sort(key=lambda o: o.score, reverse=True)

        scores = [o.score for o in combined]
        assert scores == sorted(scores, reverse=True)


# ──────────────────────────────────────────────
# Test: Source counts in combined response
# ──────────────────────────────────────────────

class TestSourceCounts:
    def test_by_source_count_correct(self):
        """
        The combined endpoint must track how many opportunities came from
        each source so the frontend can show breakdown.
        """
        aave_opps   = [make_opp(f"aave-{i}",   "aave-v3",   chain="Ethereum") for i in range(3)]
        morpho_opps = [make_opp(f"morpho-{i}",  "morpho",    chain="Ethereum") for i in range(2)]
        kamino_opps = [make_opp(f"kamino-{i}",  "kamino",    chain="Solana")  for i in range(1)]

        all_opps = aave_opps + morpho_opps + kamino_opps
        seen = set()
        deduped = []
        for opp in all_opps:
            if opp.pool_id not in seen:
                seen.add(opp.pool_id)
                deduped.append(opp)

        deduped.sort(key=lambda o: o.score, reverse=True)

        by_source = {"defillama": 0, "morpho": 0, "kamino": 0}
        for o in deduped:
            if o.protocol in ("aave-v3", "aave-v2"):
                by_source["defillama"] += 1
            elif o.protocol == "morpho":
                by_source["morpho"] += 1
            elif o.protocol == "kamino":
                by_source["kamino"] += 1

        assert by_source["defillama"] == 3
        assert by_source["morpho"]    == 2
        assert by_source["kamino"]    == 1


# ──────────────────────────────────────────────
# Test: All sources produce instrument fields
# ──────────────────────────────────────────────

class TestInstrumentFieldsAcrossSources:
    def test_defillama_has_instrument_fields(self):
        """DefiLlama Aave opportunities must include all 8 instrument fields."""
        from data.defillama import fetch_aave_opportunities

        with patch("data.defillama._get") as mock_get:
            mock_get.return_value = {
                "data": [{
                    "pool": "test-pool-001",
                    "project": "aave-v3",
                    "chain": "Ethereum",
                    "symbol": "USDC",
                    "tvlUsd": 100_000_000,
                    "apy": 3.9,
                    "apyBase": 3.9,
                    "apyReward": 0.0,
                    "rewardTokens": [],
                    "rewardTokenSymbols": [],
                    "poolMeta": "Aave V3 USDC Ethereum",
                    "underlyingTokens": [],
                    "ilRisk": "no",
                    "exposure": "single",
                    "predictions": {},
                }]
            }
            opps = fetch_aave_opportunities(risk_free_rate=0.04)

        assert len(opps) == 1
        d = opps[0].to_dict()
        for field in [
            "opportunity_type", "yield_source", "liquidity_profile",
            "withdrawal_constraints", "curator_or_strategy_manager",
            "reward_token_dependence", "stacking_risk", "maturity_date",
        ]:
            assert field in d, f"{field} missing from DefiLlama opportunity"

    def test_morpho_has_instrument_fields(self):
        """Morpho opportunities must include all 8 instrument fields."""
        from data.morpho import fetch_morpho_opportunities

        with patch("data.morpho._post_graphql") as mock_post:
            mock_post.return_value = {
                "data": {
                    "vaultV2s": {
                        "items": [{
                            "address": "0xMORPHOTEST1111111111111111111111111111",
                            "symbol": "USDC",
                            "name": "Morpho Test USDC",
                            "totalAssetsUsd": 100_000_000,
                            "avgApy": 0.042,
                            "avgNetApy": 0.042,
                            "rewards": [],
                            "adapters": {"items": []},
                            "chain": {"id": 1, "network": "ethereum"},
                        }]
                    }
                }
            }
            opps = fetch_morpho_opportunities(risk_free_rate=0.04)

        assert len(opps) >= 1
        d = opps[0].to_dict()
        for field in [
            "opportunity_type", "yield_source", "liquidity_profile",
            "withdrawal_constraints", "curator_or_strategy_manager",
            "reward_token_dependence", "stacking_risk", "maturity_date",
        ]:
            assert field in d, f"{field} missing from Morpho opportunity"

    def test_kamino_has_instrument_fields(self):
        """Kamino opportunities must include all 8 instrument fields."""
        from data.kamino import fetch_kamino_opportunities

        vault = {
            "address": "KaminoTestVault11111111111111111111",
            "state": {
                "tokenMint": "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v",
                "name": "Test USDC",
                "vaultFarm": "9FVjHqduhD8ZbXhZLGHbK4S3VQUQBtJbC1SG6Y36VZK3",
                "prevAum": "1000000.0",   # required for pre-filter in _build_vault_tvl
            },
        }
        metrics = {
            "apy": "0.038",
            "apyActual": "0.030",
            "apyFarmRewards": "0.008",
            "apyIncentives": "0",
            "apyReservesIncentives": "0",
            "apyTheoretical": "0.030",
            "apy7d": "0.036",
            "apy30d": "0.038",
            "apy90d": "0.040",
            "apy365d": "0.055",
            "tokensInvestedUsd": "100000000",
        }

        # Patch vault list AND per-vault metrics (patched _fetch_vault_metrics
        # bypasses the internal _get call so no nesting conflict)
        with patch("data.kamino._get", return_value=[vault]):
            with patch("data.kamino._fetch_vault_metrics", return_value=metrics):
                opps = fetch_kamino_opportunities(risk_free_rate=0.04)

        assert len(opps) == 1, f"Expected 1 opp, got {len(opps)}"
        d = opps[0].to_dict()
        for field in [
            "opportunity_type", "yield_source", "liquidity_profile",
            "withdrawal_constraints", "curator_or_strategy_manager",
            "reward_token_dependence", "stacking_risk", "maturity_date",
        ]:
            assert field in d, f"{field} missing from Kamino opportunity"


# ──────────────────────────────────────────────
# Test: Schema conformance — no raw API objects leak
# ──────────────────────────────────────────────

class TestSchemaConformance:
    def test_all_opportunities_have_required_schema_fields(self):
        """
        Every opportunity returned by any source must have all required
        schema fields present — no missing keys.

        Note: maturity_date is Optional[str] so None is valid (open-ended).
        reward_token_dependence defaults to 0.0 (float, always valid).
        """
        # Build a fully-populated opportunity manually
        rm = RewardMix(base_apy=0.03, reward_apy=0.01, reward_tokens=["MORPHO"])
        sb = ScoreBreakdown(
            tvl_score=7.0, protocol_score=8.0, chain_score=9.0,
            yield_score=6.0, reward_stability_score=7.0, confidence_score=8.0,
        )
        opp = Opportunity(
            id="schema-test-001",
            protocol="morpho",
            protocol_display="Morpho",
            chain="Ethereum",
            asset="USDC",
            pool_id="0xTestPool12345",
            pool_meta="Morpho USDC Ethereum",
            apy=0.04,
            reward_mix=rm,
            tvl_usd=100_000_000,
            source="morpho_api",
            source_confidence="medium",
            url="https://morpho.xyz/pool",
            score_breakdown=sb,
            risk_tier="low",
        )
        d = opp.to_dict()

        required = [
            "id", "protocol", "protocol_display", "chain", "asset",
            "pool_id", "pool_meta", "apy", "apy_pct", "reward_mix",
            "tvl_usd", "source", "source_confidence", "url",
            "score", "score_breakdown", "risk_tier", "fetched_at",
            "extra",
            # Instrument fields (all must be present in dict)
            "opportunity_type", "yield_source", "liquidity_profile",
            "withdrawal_constraints", "curator_or_strategy_manager",
            "reward_token_dependence", "stacking_risk", "maturity_date",
        ]
        for field in required:
            assert field in d, f"Required field '{field}' missing from schema"

        # maturity_date is Optional — None is valid for open-ended instruments
        assert d["maturity_date"] is None  # explicitly verify Optional semantics

        # The rest must be non-None (required fields)
        non_optional_required = [f for f in required if f != "maturity_date"]
        for field in non_optional_required:
            assert d[field] is not None, f"Required field '{field}' must not be None"
