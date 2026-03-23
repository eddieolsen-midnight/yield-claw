"""
Kamino Finance Solana adapter.

Docs: https://docs.kamino.finance/
API base: https://api.kamino.finance

Kamino is a Solana-native DeFi protocol offering lending (Kamino Lend)
and automated yield vaults (Kamino Earn).

APY source: per-vault /kvaults/vaults/{address}/metrics endpoint.
TVL source: prevAum from vault state (total AUM in tokens).

NOTE: Kamino vaults run on Solana epochs (shorter than calendar days),
so liquidity_profile is INTERVAL and withdrawal_constraints is "Epoch-based".
"""

import requests
from typing import Optional

from models.scoring import build_opportunity

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────

KAMINO_BASE = "https://api.kamino.finance"
DEFAULT_TIMEOUT = 10  # seconds

# USDC mint on Solana
USDC_MINT = "EPjFWdd5AufqSSqeM2qN1xzybapC8G4wEGGkZwyTDt1v"

# Kamino protocol identifiers
PROTOCOL = "kamino"
PROTOCOL_DISPLAY = "Kamino"

# Source confidence: API-based = medium
KAMINO_CONFIDENCE = "medium"

# Pool URL template
POOL_URL_TEMPLATE = "https://app.kamino.finance/vaults/{address}"

# Minimum TVL in USD to include a vault (matches defillama.py threshold)
MIN_TVL_USD = 100_000

# ──────────────────────────────────────────────
# Add Solana to chain scores if not present
# ──────────────────────────────────────────────

import models.scoring as scoring_module

if "solana" not in scoring_module.CHAIN_SCORES:
    scoring_module.CHAIN_SCORES["solana"] = 8.0  # Solana is battle-tested

# ──────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────

def _get(url: str, params: dict = None) -> dict:
    """GET with error handling. Raises on non-2xx."""
    resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────

def _fetch_vault_metrics(address: str) -> Optional[dict]:
    """
    Fetch APY metrics for a single vault.
    Returns the metrics dict or None on failure.
    """
    try:
        return _get(f"{KAMINO_BASE}/kvaults/vaults/{address}/metrics")
    except Exception:
        return None


def _build_vault_tvl(state: dict) -> float:
    """
    Extract TVL in USD from vault state.

    NOTE: prevAum from the vault state is NOT the current TVL - it's
    a cumulative or historical figure that doesn't convert cleanly to USD
    via mint decimals alone (the numbers don't work: $63T for Steakhouse).

    The correct TVL source is tokensInvestedUsd from the per-vault
    /metrics endpoint. This function is only used as a pre-filter
    before we have metrics data; we use a very low threshold to avoid
    false negatives.
    """
    prev_aum = float(state.get("prevAum", 0))
    # Conservative pre-filter: skip vaults with prevAum < 1 (essentially zero)
    return prev_aum


def _build_opportunity_from_vault(
    vault: dict,
    risk_free_rate: float,
) -> Optional[object]:
    """
    Build an Opportunity from a single vault dict + its metrics.
    Returns None if the vault should be skipped.
    """
    state = vault.get("state", {})
    address = vault.get("address", "")

    # ── Filter: USDC only ──
    token_mint = state.get("tokenMint", "")
    if token_mint != USDC_MINT:
        return None

    # ── TVL pre-filter (before metrics API call) ──
    # We use prevAum as a rough pre-filter; actual TVL comes from metrics.
    # prevAum units vary by vault — use a very low threshold to avoid
    # false negatives. Real $100k TVL check happens after metrics fetch.
    if _build_vault_tvl(state) < 0.001:
        return None

    # ── Fetch metrics (APY data) ──
    metrics = _fetch_vault_metrics(address)
    if not metrics:
        return None

    # apy is a decimal like 0.01419 = 1.419%
    apy = float(metrics.get("apy", 0))

    # If we have no meaningful APY, skip
    if apy <= 0:
        return None

    # TVL from metrics tokensInvestedUsd (correct source, not prevAum)
    tvl_usd = float(metrics.get("tokensInvestedUsd", 0))
    if tvl_usd < MIN_TVL_USD:
        return None

    # apyActual = realized yield, apyTheoretical = expected organic yield
    apy_base = float(metrics.get("apyActual", apy))
    apy_reward = (
        float(metrics.get("apyFarmRewards", 0))
        + float(metrics.get("apyIncentives", 0))
        + float(metrics.get("apyReservesIncentives", 0))
    )

    # ── Reward tokens: Kamino vault rewards are typically SOL or other tokens
    # The metrics don't directly list reward token symbols; we use "Kamino Vault Rewards"
    reward_tokens = ["Kamino Vault Rewards"]

    name = state.get("name", "Kamino USDC Vault")
    pool_meta = f"{PROTOCOL_DISPLAY} {name} Solana"
    url = POOL_URL_TEMPLATE.format(address=address)

    # opportunity_type: LENDING for Kamino lending/earn vaults
    opportunity_type = "LENDING"
    yield_source = "supply_interest"
    liquidity_profile = "INTERVAL"
    withdrawal_constraints = "Epoch-based"
    curator_or_strategy_manager = "Kamino Team"
    reward_token_dependence = 0.0  # base yield is primary
    stacking_risk = "LOW"
    maturity_date = None

    return build_opportunity(
        pool_id=address,
        protocol=PROTOCOL,
        protocol_display=PROTOCOL_DISPLAY,
        chain="Solana",
        asset="USDC",
        pool_meta=pool_meta,
        apy=apy,
        apy_base=apy_base,
        apy_reward=apy_reward,
        reward_tokens=reward_tokens,
        tvl_usd=tvl_usd,
        source="kamino_api",
        source_confidence=KAMINO_CONFIDENCE,
        url=url,
        risk_free_rate=risk_free_rate,
        extra={
            "vault_name": name,
            "apy7d": metrics.get("apy7d"),
            "apy30d": metrics.get("apy30d"),
            "apy90d": metrics.get("apy90d"),
            "apyFarmRewards": metrics.get("apyFarmRewards"),
            "apyIncentives": metrics.get("apyIncentives"),
            "apyReservesIncentives": metrics.get("apyReservesIncentives"),
            "vaultFarm": state.get("vaultFarm"),
            "performanceFeeBps": state.get("performanceFeeBps"),
            "managementFeeBps": state.get("managementFeeBps"),
        },
        # Instrument type fields
        opportunity_type=opportunity_type,
        yield_source=yield_source,
        liquidity_profile=liquidity_profile,
        withdrawal_constraints=withdrawal_constraints,
        curator_or_strategy_manager=curator_or_strategy_manager,
        reward_token_dependence=reward_token_dependence,
        stacking_risk=stacking_risk,
        maturity_date=maturity_date,
    )


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def fetch_kamino_opportunities(
    risk_free_rate: Optional[float] = None,
) -> list:
    """
    Fetch Kamino Finance USDC vault opportunities on Solana.

    Args:
        risk_free_rate: Override risk-free rate. If None, falls back to 0.04.

    Returns:
        List of Opportunity objects, sorted by composite score descending.
    """
    if risk_free_rate is None:
        risk_free_rate = 0.04

    opportunities = []

    try:
        vaults = _get(f"{KAMINO_BASE}/kvaults/vaults")
    except Exception:
        return []  # graceful fallback

    for vault in vaults:
        opp = _build_opportunity_from_vault(vault, risk_free_rate)
        if opp is not None:
            opportunities.append(opp)

    # Sort by composite score descending
    opportunities.sort(key=lambda o: o.score, reverse=True)
    return opportunities
