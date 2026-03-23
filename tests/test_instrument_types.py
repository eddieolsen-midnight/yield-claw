"""
Tests for the 8 instrument-type fields on Opportunity.

Covers:
- All 8 fields present in to_dict() output
- build_opportunity accepts all 8 fields
- Defaults applied when fields not provided
"""

import pytest
from models.opportunity import Opportunity, RewardMix, ScoreBreakdown
from models.scoring import build_opportunity


# ──────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────

def make_minimal_opportunity(**overrides):
    """Factory for a bare-minimum Opportunity used in tests."""
    reward_mix = RewardMix(base_apy=0.03, reward_apy=0.01, reward_tokens=["OP"])
    score_breakdown = ScoreBreakdown(
        tvl_score=7.0,
        protocol_score=8.0,
        chain_score=9.0,
        yield_score=6.0,
        reward_stability_score=7.0,
        confidence_score=8.0,
    )
    kw = dict(
        id="aave-v3-ethereum-usdc-abc12345",
        protocol="aave-v3",
        protocol_display="Aave V3",
        chain="Ethereum",
        asset="USDC",
        pool_id="abc12345",
        pool_meta="Aave V3 USDC Ethereum",
        apy=0.04,
        reward_mix=reward_mix,
        tvl_usd=100_000_000,
        source="defillama",
        source_confidence="medium",
        url="https://defillama.com/yields/pool/abc12345",
        score_breakdown=score_breakdown,
        risk_tier="low",
    )
    kw.update(overrides)
    return Opportunity(**kw)


# ──────────────────────────────────────────────
# Test: all 8 fields in to_dict()
# ──────────────────────────────────────────────

def test_to_dict_includes_all_instrument_fields():
    opp = make_minimal_opportunity(
        opportunity_type="LENDING",
        yield_source="supply_interest",
        liquidity_profile="INSTANT",
        withdrawal_constraints="None",
        curator_or_strategy_manager="Aave Governance",
        reward_token_dependence=0.25,
        stacking_risk="NONE",
        maturity_date="2025-12-31",
    )
    d = opp.to_dict()

    assert "opportunity_type" in d
    assert "yield_source" in d
    assert "liquidity_profile" in d
    assert "withdrawal_constraints" in d
    assert "curator_or_strategy_manager" in d
    assert "reward_token_dependence" in d
    assert "stacking_risk" in d
    assert "maturity_date" in d

    assert d["opportunity_type"] == "LENDING"
    assert d["yield_source"] == "supply_interest"
    assert d["liquidity_profile"] == "INSTANT"
    assert d["withdrawal_constraints"] == "None"
    assert d["curator_or_strategy_manager"] == "Aave Governance"
    assert d["reward_token_dependence"] == 0.25
    assert d["stacking_risk"] == "NONE"
    assert d["maturity_date"] == "2025-12-31"


# ──────────────────────────────────────────────
# Test: build_opportunity accepts all 8 fields
# ──────────────────────────────────────────────

def test_build_opportunity_accepts_all_instrument_fields():
    opp = build_opportunity(
        pool_id="pool-xyz-999",
        protocol="aave-v3",
        protocol_display="Aave V3",
        chain="Polygon",
        asset="USDC",
        pool_meta="Aave V3 USDC Polygon",
        apy=0.045,
        apy_base=0.035,
        apy_reward=0.01,
        reward_tokens=["WMATIC"],
        tvl_usd=50_000_000,
        source="defillama",
        source_confidence="medium",
        url="https://defillama.com/yields/pool/pool-xyz-999",
        opportunity_type="LENDING",
        yield_source="supply_interest",
        liquidity_profile="INSTANT",
        withdrawal_constraints="None",
        curator_or_strategy_manager="Aave Governance",
        reward_token_dependence=0.22,
        stacking_risk="LOW",
        maturity_date="2026-06-30",
    )

    d = opp.to_dict()
    assert d["opportunity_type"] == "LENDING"
    assert d["yield_source"] == "supply_interest"
    assert d["liquidity_profile"] == "INSTANT"
    assert d["withdrawal_constraints"] == "None"
    assert d["curator_or_strategy_manager"] == "Aave Governance"
    assert d["reward_token_dependence"] == 0.22
    assert d["stacking_risk"] == "LOW"
    assert d["maturity_date"] == "2026-06-30"


# ──────────────────────────────────────────────
# Test: defaults applied when fields not provided
# ──────────────────────────────────────────────

def test_build_opportunity_instrument_field_defaults():
    """
    When instrument-type fields are not passed to build_opportunity,
    sensible defaults should be applied.
    """
    opp = build_opportunity(
        pool_id="pool-abc-123",
        protocol="morpho",
        protocol_display="Morpho",
        chain="Ethereum",
        asset="USDC",
        pool_meta="Morpho USDC Ethereum",
        apy=0.04,
        apy_base=0.03,
        apy_reward=0.01,
        reward_tokens=["MORPHO"],
        tvl_usd=25_000_000,
        source="morpho_api",
        source_confidence="high",
        url="https://morpho.xyz/pools",
    )

    d = opp.to_dict()

    # Defaults as specified in the task
    assert d["opportunity_type"] == "LENDING"
    assert d["yield_source"] == "supply_interest"
    assert d["liquidity_profile"] == "INSTANT"
    assert d["withdrawal_constraints"] == "None"
    assert d["curator_or_strategy_manager"] == ""
    assert d["reward_token_dependence"] == 0.0
    assert d["stacking_risk"] == "NONE"
    assert d["maturity_date"] is None


def test_opportunity_direct_construct_all_defaults():
    """
    When Opportunity is constructed directly with no instrument fields,
    all 8 should get their default values.
    """
    reward_mix = RewardMix(base_apy=0.02, reward_apy=0.01, reward_tokens=["OP"])
    score_breakdown = ScoreBreakdown(
        tvl_score=5.0, protocol_score=5.0, chain_score=5.0,
        yield_score=5.0, reward_stability_score=5.0, confidence_score=5.0,
    )
    opp = Opportunity(
        id="test-123",
        protocol="test-protocol",
        protocol_display="Test Protocol",
        chain="Ethereum",
        asset="USDC",
        pool_id="pool-123",
        pool_meta="Test USDC Ethereum",
        apy=0.03,
        reward_mix=reward_mix,
        tvl_usd=1_000_000,
        source="test",
        source_confidence="medium",
        url="https://example.com",
        score_breakdown=score_breakdown,
        risk_tier="medium",
    )

    d = opp.to_dict()
    assert d["opportunity_type"] == ""
    assert d["yield_source"] == ""
    assert d["liquidity_profile"] == ""
    assert d["withdrawal_constraints"] == ""
    assert d["curator_or_strategy_manager"] == ""
    assert d["reward_token_dependence"] == 0.0
    assert d["stacking_risk"] == ""
    assert d["maturity_date"] is None
