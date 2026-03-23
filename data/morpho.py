"""
Morpho Protocol GraphQL adapter.

Fetches vault data from the Morpho GraphQL API and normalizes it
to the Opportunity schema defined in models/opportunity.py.

API endpoint: https://api.morpho.org/graphql
APY from Morpho is already decimal (0.038 = 3.8%), NOT a percentage string.
"""

import requests
from typing import Optional

from models.scoring import build_opportunity
from models.opportunity import Opportunity

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────

MORPHO_GRAPHQL_URL = "https://api.morpho.org/graphql"

DEFAULT_TIMEOUT = 10  # seconds

# Morpho source confidence: aggregator API = medium
MORPHO_CONFIDENCE = "medium"

# Stablecoins we care about for treasury management
TARGET_ASSETS = {"USDC", "USDT", "DAI"}

# Chain ID → display name
CHAIN_DISPLAY = {
    1:   "Ethereum",
    8453: "Base",
}

# Protocol display name
PROTOCOL_DISPLAY = "Morpho"

# Pool URL template
POOL_URL_TEMPLATE = "https://app.morpho.org/vault/{address}"

# Minimum TVL threshold (skip pools below this)
MIN_TVL_USD = 100_000


# ──────────────────────────────────────────────
# GraphQL query
# ──────────────────────────────────────────────

GRAPHQL_QUERY = """
query FetchVaults($first: Int!, $chainIds: [Int!]) {
  vaultV2s(
    first: $first
    where: { chainId_in: $chainIds }
  ) {
    items {
      address
      symbol
      name
      totalAssetsUsd
      totalAssets
      avgApy
      avgNetApy
      rewards {
        asset {
          address
        }
        supplyApr
        yearlySupplyTokens
      }
      adapters {
        items {
          assetsUsd
          type
        }
      }
      chain {
        id
        network
      }
    }
  }
}
"""


# ──────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────

def _post_graphql(query: str, variables: dict = None) -> dict:
    """POST GraphQL request with error handling. Raises on non-2xx."""
    resp = requests.post(
        MORPHO_GRAPHQL_URL,
        json={"query": query, "variables": variables or {}},
        timeout=DEFAULT_TIMEOUT,
    )
    resp.raise_for_status()
    return resp.json()


# ──────────────────────────────────────────────
# Normalization
# ──────────────────────────────────────────────

def _normalize_vault(vault: dict, risk_free_rate: float) -> Optional[Opportunity]:
    """
    Map a single Morpho vault dict to an Opportunity.
    Returns None if the vault should be skipped.
    """
    symbol = (vault.get("symbol") or "").upper()
    chain_id = vault.get("chain", {}).get("id")
    chain_display = CHAIN_DISPLAY.get(chain_id, f"Chain-{chain_id}")
    address = vault.get("address") or ""

    # Skip non-stablecoin vaults
    if symbol not in TARGET_ASSETS:
        return None

    # Skip vaults with no address
    if not address:
        return None

    tvl_usd = float(vault.get("totalAssetsUsd") or 0.0)

    # Skip low-liquidity vaults (< $100k)
    if tvl_usd < MIN_TVL_USD:
        return None

    # APY is already decimal from Morpho (e.g. 0.038 = 3.8%)
    apy_raw = vault.get("avgApy")
    avg_net_apy_raw = vault.get("avgNetApy")

    if apy_raw is None:
        return None

    apy = float(apy_raw)

    # avgNetApy is the net APY after rewards — use as base
    # If avgNetApy is not available, use avgApy as base
    if avg_net_apy_raw is not None:
        apy_base = float(avg_net_apy_raw)
    else:
        apy_base = apy

    # Reward APY = total APY - base APY (if positive)
    apy_reward = max(0.0, apy - apy_base)

    # Reward tokens from the rewards array
    rewards = vault.get("rewards") or []
    reward_token_symbols = [
        r.get("asset", {}).get("address", f"TOKEN_{i}")
        for i, r in enumerate(rewards)
        if r.get("asset")
    ]

    # Fallback to count-based placeholder symbols if no addresses found
    if not reward_token_symbols and rewards:
        reward_token_symbols = [f"MORPHO_REWARD_{i}" for i in range(len(rewards))]

    pool_meta = f"Morpho {symbol} {chain_display}"
    url = POOL_URL_TEMPLATE.format(address=address)

    return build_opportunity(
        pool_id=address,
        protocol="morpho",
        protocol_display=PROTOCOL_DISPLAY,
        chain=chain_display,
        asset=symbol,
        pool_meta=pool_meta,
        apy=apy,
        apy_base=apy_base,
        apy_reward=apy_reward,
        reward_tokens=reward_token_symbols,
        tvl_usd=tvl_usd,
        source="morpho_api",
        source_confidence=MORPHO_CONFIDENCE,
        url=url,
        risk_free_rate=risk_free_rate,
        extra={
            "morpho_address": address,
            "morpho_name": vault.get("name"),
            "total_assets": vault.get("totalAssets"),
            "avg_net_apy": avg_net_apy_raw,
            "adapters": vault.get("adapters", {}).get("items", []),
        },
    )


# ──────────────────────────────────────────────
# Public API
# ──────────────────────────────────────────────

def fetch_morpho_opportunities(
    chains: Optional[list] = None,
    risk_free_rate: Optional[float] = None,
) -> list[Opportunity]:
    """
    Fetch Morpho stablecoin vault opportunities.

    Args:
        chains: list of chain display names to include, e.g. ["Ethereum", "Base"]
                None = all supported chains (Ethereum, Base)
        risk_free_rate: override; if None, defaults to 0.04 (4%)

    Returns:
        List of Opportunity objects, sorted by composite score descending.
    """
    if risk_free_rate is None:
        risk_free_rate = 0.04

    # Map chain display names to chain IDs
    CHAIN_DISPLAY_TO_ID = {v: k for k, v in CHAIN_DISPLAY.items()}

    if chains:
        chain_ids = [CHAIN_DISPLAY_TO_ID[c] for c in chains if c in CHAIN_DISPLAY_TO_ID]
        if not chain_ids:
            return []
    else:
        chain_ids = list(CHAIN_DISPLAY.keys())

    try:
        data = _post_graphql(
            GRAPHQL_QUERY,
            variables={"first": 100, "chainIds": chain_ids},
        )
    except Exception:
        # Network or API error — return empty list gracefully
        return []

    vaults = (
        data.get("data", {})
        .get("vaultV2s", {})
        .get("items", [])
    )

    opportunities = []
    for vault in vaults:
        opp = _normalize_vault(vault, risk_free_rate)
        if opp is not None:
            opportunities.append(opp)

    # Sort by composite score descending
    opportunities.sort(key=lambda o: o.score, reverse=True)
    return opportunities
