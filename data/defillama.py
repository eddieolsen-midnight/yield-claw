"""
DefiLlama API client.

Primary data source (L1). Free, no auth required.
Docs: https://api-docs.defillama.com

All methods return normalized Opportunity objects — never raw API dicts.
"""

import requests
from typing import Optional
from models.scoring import build_opportunity

# ──────────────────────────────────────────────
# Config
# ──────────────────────────────────────────────

YIELDS_BASE = "https://yields.llama.fi"
LLAMA_BASE = "https://api.llama.fi"

DEFAULT_TIMEOUT = 10  # seconds

# DefiLlama source confidence: well-known aggregator = medium
# (Direct contract reads would be high)
DEFILLAMA_CONFIDENCE = "medium"

# Stablecoins we care about for treasury management
TARGET_ASSETS = {"USDC", "USDT", "DAI", "USDC.E", "USDC.e", "USDT.E"}

# Protocols in Phase 1 scope
PHASE1_PROTOCOLS = {"aave-v3", "aave-v2"}

# Protocol display names
PROTOCOL_DISPLAY = {
    "aave-v3": "Aave V3",
    "aave-v2": "Aave V2",
    "morpho":  "Morpho",
    "pendle":  "Pendle",
}

# Chain display names (DefiLlama uses title-case already for most)
CHAIN_DISPLAY = {
    "polygon": "Polygon",
    "ethereum": "Ethereum",
    "arbitrum": "Arbitrum",
    "optimism": "Optimism",
    "base": "Base",
}

# Pool URL template for DefiLlama
POOL_URL_TEMPLATE = "https://defillama.com/yields/pool/{pool_id}"


# ──────────────────────────────────────────────
# HTTP helpers
# ──────────────────────────────────────────────

def _get(url: str, params: dict = None) -> dict:
    """GET with error handling. Raises on non-2xx."""
    resp = requests.get(url, params=params, timeout=DEFAULT_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


# ──────────────────────────────────────────────
# Risk-free rate
# ──────────────────────────────────────────────

def fetch_risk_free_rate() -> float:
    """
    Fetch current risk-free rate = Aave V3 USDC on Ethereum supply APY.
    Falls back to 0.04 (4%) if the fetch fails.
    """
    try:
        data = _get(f"{YIELDS_BASE}/pools")
        pools = data.get("data", [])
        for pool in pools:
            if (
                pool.get("project") == "aave-v3"
                and pool.get("chain", "").lower() == "ethereum"
                and pool.get("symbol", "").upper() in {"USDC", "USDC.E"}
            ):
                apy = pool.get("apy")
                if apy is not None:
                    return float(apy) / 100  # DefiLlama returns % (e.g. 3.8 = 3.8%)
    except Exception:
        pass
    return 0.04  # fallback


# ──────────────────────────────────────────────
# Pool fetching
# ──────────────────────────────────────────────

def _normalize_pool(pool: dict, risk_free_rate: float):
    """
    Map a single DefiLlama pool dict to an Opportunity.
    Returns None if the pool should be skipped.
    """
    project = pool.get("project", "").lower()
    symbol = (pool.get("symbol") or "").upper()
    chain = (pool.get("chain") or "").lower()
    pool_id = pool.get("pool", "")
    tvl_usd = pool.get("tvlUsd") or 0.0

    # Skip low-liquidity pools (< $100k)
    if tvl_usd < 100_000:
        return None

    # DefiLlama returns APY as percentage, e.g. 3.8 = 3.8%
    apy_raw = pool.get("apy") or 0.0
    apy_base_raw = pool.get("apyBase") or 0.0
    apy_reward_raw = pool.get("apyReward") or 0.0

    apy = float(apy_raw) / 100
    apy_base = float(apy_base_raw) / 100
    apy_reward = float(apy_reward_raw) / 100

    # Reward tokens
    reward_tokens_raw = pool.get("rewardTokens") or []
    # DefiLlama gives contract addresses; use underlyingTokens symbols if available
    # For now, use count as proxy — symbols resolved separately if needed
    reward_token_symbols = pool.get("rewardTokenSymbols") or (
        [f"TOKEN_{i}" for i in range(len(reward_tokens_raw))] if reward_tokens_raw else []
    )

    pool_meta = pool.get("poolMeta") or f"{PROTOCOL_DISPLAY.get(project, project)} {symbol} {chain.title()}"
    url = POOL_URL_TEMPLATE.format(pool_id=pool_id)

    chain_display = CHAIN_DISPLAY.get(chain, chain.title())
    protocol_display = PROTOCOL_DISPLAY.get(project, project.title())

    return build_opportunity(
        pool_id=pool_id,
        protocol=project,
        protocol_display=protocol_display,
        chain=chain_display,
        asset=symbol,
        pool_meta=pool_meta,
        apy=apy,
        apy_base=apy_base,
        apy_reward=apy_reward,
        reward_tokens=reward_token_symbols,
        tvl_usd=float(tvl_usd),
        source="defillama",
        source_confidence=DEFILLAMA_CONFIDENCE,
        url=url,
        risk_free_rate=risk_free_rate,
        extra={
            "defillama_pool_id": pool_id,
            "underlying_tokens": pool.get("underlyingTokens") or [],
            "il_risk": pool.get("ilRisk"),
            "exposure": pool.get("exposure"),
            "predictions": pool.get("predictions") or {},
        },
    )


def fetch_aave_opportunities(
    chains: Optional[list] = None,
    risk_free_rate: Optional[float] = None,
) -> list:
    """
    Fetch Aave V3 (and V2) stablecoin opportunities from DefiLlama.

    Args:
        chains: list of chain names to include, e.g. ["Polygon", "Ethereum"]
                None = all chains
        risk_free_rate: override; if None, fetched automatically

    Returns:
        List of Opportunity objects, sorted by composite score descending.
    """
    if risk_free_rate is None:
        risk_free_rate = fetch_risk_free_rate()

    data = _get(f"{YIELDS_BASE}/pools")
    pools = data.get("data", [])

    chain_filter = {c.lower() for c in chains} if chains else None

    opportunities = []
    for pool in pools:
        project = pool.get("project", "").lower()
        if project not in PHASE1_PROTOCOLS:
            continue

        symbol = (pool.get("symbol") or "").upper().replace("-", ".")
        # Match on base asset (USDC, USDT, DAI — strip suffixes like .E)
        base_asset = symbol.split(".")[0]
        if base_asset not in {"USDC", "USDT", "DAI"}:
            continue

        if chain_filter:
            pool_chain = (pool.get("chain") or "").lower()
            if pool_chain not in chain_filter:
                continue

        opp = _normalize_pool(pool, risk_free_rate)
        if opp is not None:
            opportunities.append(opp)

    # Sort by composite score descending
    opportunities.sort(key=lambda o: o.score, reverse=True)
    return opportunities


def fetch_all_opportunities(risk_free_rate: Optional[float] = None) -> list:
    """
    Phase 1: only Aave. Morpho and Pendle added in later phases.
    """
    if risk_free_rate is None:
        risk_free_rate = fetch_risk_free_rate()

    return fetch_aave_opportunities(risk_free_rate=risk_free_rate)
