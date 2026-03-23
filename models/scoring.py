"""
Scoring model — 6 sub-scores → weighted composite.

Each sub-score is 0–10. The composite (via ScoreBreakdown.composite) scales to 0–100.
Higher = better opportunity (safer + more yield per unit risk).
"""

import math
from models.opportunity import RewardMix, ScoreBreakdown, Opportunity, score_to_risk_tier


# ──────────────────────────────────────────────
# 1. TVL Score (0–10)
# Larger TVL = more market consensus + deeper liquidity
# ──────────────────────────────────────────────

TVL_THRESHOLDS = [
    (1_000_000_000, 10.0),   # $1B+
    (500_000_000,    9.0),   # $500M+
    (100_000_000,    8.0),   # $100M+
    (50_000_000,     7.0),   # $50M+
    (20_000_000,     6.0),   # $20M+
    (10_000_000,     5.0),   # $10M+
    (5_000_000,      4.0),   # $5M+
    (1_000_000,      3.0),   # $1M+
    (0,              1.0),   # <$1M
]

def tvl_score(tvl_usd: float) -> float:
    for threshold, score in TVL_THRESHOLDS:
        if tvl_usd >= threshold:
            return score
    return 1.0


# ──────────────────────────────────────────────
# 2. Protocol Score (0–10)
# Reflects audit history, time in production, track record
# ──────────────────────────────────────────────

PROTOCOL_SCORES = {
    "aave-v3":    10.0,   # battle-tested, heavily audited
    "aave-v2":     9.0,
    "compound-v3": 9.0,
    "compound-v2": 8.5,
    "morpho":      8.0,   # newer but well-audited
    "spark":       8.0,
    "pendle":      7.5,   # complex mechanics, good audits
    "euler":       6.0,   # experienced exploit in v1
    "default":     5.0,   # unknown / unranked protocol
}

def protocol_score(protocol: str) -> float:
    return PROTOCOL_SCORES.get(protocol.lower(), PROTOCOL_SCORES["default"])


# ──────────────────────────────────────────────
# 3. Chain Score (0–10)
# Reflects chain security, decentralization, track record
# ──────────────────────────────────────────────

CHAIN_SCORES = {
    "ethereum":  10.0,
    "polygon":    8.0,
    "arbitrum":   8.5,
    "optimism":   8.5,
    "base":       8.0,
    "avalanche":  7.5,
    "bnb":        7.0,
    "gnosis":     7.5,
    "default":    5.0,
}

def chain_score(chain: str) -> float:
    return CHAIN_SCORES.get(chain.lower(), CHAIN_SCORES["default"])


# ──────────────────────────────────────────────
# 4. Yield Score (0–10)
# Captures excess APY above the risk-free rate.
# NOT purely "more yield = better" — this scores
# yield attractiveness relative to the baseline.
# ──────────────────────────────────────────────

def yield_score(apy: float, risk_free_rate: float) -> float:
    """
    Score excess yield attractiveness.
    - Negative or zero excess → low score (might as well use risk-free)
    - Small positive excess (0–1%) → moderate score
    - Good excess (1–3%) → high score
    - Very high excess (>3%) → tapers off (excess risk signal)
    """
    excess_pct = (apy - risk_free_rate) * 100  # convert to percentage points

    if excess_pct <= 0:
        return 2.0   # at or below risk-free; not compelling but not zero
    elif excess_pct <= 0.5:
        return 4.0
    elif excess_pct <= 1.0:
        return 6.0
    elif excess_pct <= 2.0:
        return 7.5
    elif excess_pct <= 3.0:
        return 9.0
    elif excess_pct <= 5.0:
        return 8.0   # starts to look suspicious — taper down
    elif excess_pct <= 10.0:
        return 6.0
    else:
        return 3.0   # >10pp above risk-free = red flag


# ──────────────────────────────────────────────
# 5. Reward Stability Score (0–10)
# Measures how much of the yield comes from base (organic) vs reward tokens.
# Base-heavy yield is more predictable/sustainable.
# ──────────────────────────────────────────────

def reward_stability_score(reward_mix: RewardMix) -> float:
    """
    Score based on the fraction of yield that is organic (base) vs token rewards.
    Threshold-based: if reward tokens make up >50% of APY, yield is unstable.
    """
    rf = reward_mix.reward_fraction  # 0 = all base, 1 = all reward tokens

    if rf <= 0.0:
        return 10.0   # 100% organic base yield
    elif rf <= 0.10:
        return 9.5
    elif rf <= 0.25:
        return 8.0
    elif rf <= 0.50:
        return 6.0
    elif rf <= 0.75:
        return 4.0
    else:
        return 2.0    # >75% token rewards — highly volatile


# ──────────────────────────────────────────────
# 6. Confidence Score (0–10)
# Data source reliability
# ──────────────────────────────────────────────

CONFIDENCE_SCORES = {
    "high":   10.0,   # direct contract read or protocol-native API
    "medium":  7.0,   # well-known aggregator (DefiLlama)
    "low":     4.0,   # estimated / derived / unverified
}

def confidence_score(source_confidence: str) -> float:
    return CONFIDENCE_SCORES.get(source_confidence.lower(), 4.0)


# ──────────────────────────────────────────────
# Main scoring function
# ──────────────────────────────────────────────

def score_opportunity(
    protocol: str,
    chain: str,
    apy: float,
    tvl_usd: float,
    reward_mix: RewardMix,
    source_confidence: str,
    risk_free_rate: float = 0.04,   # ~4% Aave V3 USDC Ethereum default
) -> ScoreBreakdown:
    """
    Compute all 6 sub-scores and return a ScoreBreakdown.

    Args:
        protocol: machine protocol name, e.g. "aave-v3"
        chain: chain name, e.g. "Ethereum"
        apy: total APY as decimal (0.038 = 3.8%)
        tvl_usd: total value locked in USD
        reward_mix: RewardMix breakdown object
        source_confidence: "high" | "medium" | "low"
        risk_free_rate: risk-free baseline APY as decimal
    """
    return ScoreBreakdown(
        tvl_score=tvl_score(tvl_usd),
        protocol_score=protocol_score(protocol),
        chain_score=chain_score(chain),
        yield_score=yield_score(apy, risk_free_rate),
        reward_stability_score=reward_stability_score(reward_mix),
        confidence_score=confidence_score(source_confidence),
    )


def build_opportunity(
    *,
    pool_id: str,
    protocol: str,
    protocol_display: str,
    chain: str,
    asset: str,
    pool_meta: str,
    apy: float,
    apy_base: float,
    apy_reward: float,
    reward_tokens: list,
    tvl_usd: float,
    source: str,
    source_confidence: str,
    url: str,
    risk_free_rate: float = 0.04,
    extra: dict = None,
) -> Opportunity:
    """
    Factory: takes raw normalized fields, runs scoring, returns a complete Opportunity.
    Use this instead of constructing Opportunity manually.
    """
    reward_mix = RewardMix(
        base_apy=apy_base,
        reward_apy=apy_reward,
        reward_tokens=reward_tokens,
    )

    breakdown = score_opportunity(
        protocol=protocol,
        chain=chain,
        apy=apy,
        tvl_usd=tvl_usd,
        reward_mix=reward_mix,
        source_confidence=source_confidence,
        risk_free_rate=risk_free_rate,
    )

    op_id = f"{protocol}-{chain.lower()}-{asset.lower()}-{pool_id[:8]}"

    return Opportunity(
        id=op_id,
        protocol=protocol,
        protocol_display=protocol_display,
        chain=chain,
        asset=asset,
        pool_id=pool_id,
        pool_meta=pool_meta,
        apy=apy,
        reward_mix=reward_mix,
        tvl_usd=tvl_usd,
        source=source,
        source_confidence=source_confidence,
        url=url,
        score_breakdown=breakdown,
        risk_tier=score_to_risk_tier(breakdown.composite),
        extra=extra or {},
    )
