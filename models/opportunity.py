"""
Normalized Opportunity object — the single schema all data must conform to
before touching the UI or scoring logic.

Rule: No raw API responses in the frontend. Everything goes through this.
"""

from dataclasses import dataclass, field, asdict
from typing import Optional
from datetime import datetime, timezone


@dataclass
class RewardMix:
    """Breakdown of what makes up the total APY."""
    base_apy: float          # supply/lending base APY (e.g. 0.038 = 3.8%)
    reward_apy: float        # incentive/token reward APY
    reward_tokens: list      # list of reward token symbols, e.g. ["MATIC", "OP"]

    @property
    def total_apy(self) -> float:
        return self.base_apy + self.reward_apy

    @property
    def reward_fraction(self) -> float:
        """What fraction of total APY comes from reward tokens (0–1)."""
        if self.total_apy == 0:
            return 0.0
        return self.reward_apy / self.total_apy

    def to_dict(self) -> dict:
        return {
            "base_apy": self.base_apy,
            "reward_apy": self.reward_apy,
            "reward_tokens": self.reward_tokens,
            "total_apy": self.total_apy,
            "reward_fraction": round(self.reward_fraction, 4),
        }


@dataclass
class ScoreBreakdown:
    """6 sub-scores that feed into the composite opportunity score."""
    tvl_score: float           # 0–10: TVL depth (larger = better)
    protocol_score: float      # 0–10: protocol maturity / track record
    chain_score: float         # 0–10: chain security / maturity
    yield_score: float         # 0–10: excess APY above risk-free rate
    reward_stability_score: float  # 0–10: how stable the yield is (base > reward = better)
    confidence_score: float    # 0–10: data source reliability

    # Weights — must sum to 1.0
    WEIGHTS = {
        "tvl_score": 0.25,
        "protocol_score": 0.20,
        "chain_score": 0.20,
        "yield_score": 0.15,
        "reward_stability_score": 0.10,
        "confidence_score": 0.10,
    }

    @property
    def composite(self) -> float:
        """Weighted composite score, 0–100."""
        raw = (
            self.tvl_score * self.WEIGHTS["tvl_score"]
            + self.protocol_score * self.WEIGHTS["protocol_score"]
            + self.chain_score * self.WEIGHTS["chain_score"]
            + self.yield_score * self.WEIGHTS["yield_score"]
            + self.reward_stability_score * self.WEIGHTS["reward_stability_score"]
            + self.confidence_score * self.WEIGHTS["confidence_score"]
        )
        return round(raw * 10, 2)  # scale 0–10 → 0–100

    def to_dict(self) -> dict:
        return {
            "tvl_score": self.tvl_score,
            "protocol_score": self.protocol_score,
            "chain_score": self.chain_score,
            "yield_score": self.yield_score,
            "reward_stability_score": self.reward_stability_score,
            "confidence_score": self.confidence_score,
            "composite": self.composite,
            "weights": self.WEIGHTS,
        }


# Risk tier thresholds (composite score)
RISK_TIERS = {
    "low":        (75, 100),   # score 75–100
    "medium":     (50, 75),    # score 50–75
    "high":       (25, 50),    # score 25–50
    "speculative": (0, 25),    # score 0–25
}


def score_to_risk_tier(composite_score: float) -> str:
    for tier, (low, high) in RISK_TIERS.items():
        if low <= composite_score <= high:
            return tier
    return "speculative"


@dataclass
class Opportunity:
    """
    Normalized yield opportunity object.

    Every data source (DefiLlama, Morpho API, Pendle API) must map to this
    schema before being used anywhere in the application.
    """
    # Identity
    id: str                        # "{protocol}-{chain}-{asset}-{pool_id[:8]}"
    protocol: str                  # machine name, e.g. "aave-v3"
    protocol_display: str          # human name, e.g. "Aave V3"
    chain: str                     # e.g. "Ethereum", "Polygon"
    asset: str                     # e.g. "USDC", "USDT"
    pool_id: str                   # upstream pool ID (DefiLlama pool UUID or contract address)
    pool_meta: str                 # descriptive label, e.g. "Aave V3 USDC Polygon"

    # Yield data — NEVER show apy without reward_mix and source_confidence
    apy: float                     # total APY as decimal (0.038 = 3.8%)
    reward_mix: RewardMix          # APY breakdown

    # Market data
    tvl_usd: float                 # total value locked in USD

    # Data provenance
    source: str                    # "defillama" | "morpho_api" | "pendle_api" | "contract"
    source_confidence: str         # "high" | "medium" | "low"
    url: str                       # link to pool on protocol/aggregator site

    # Scoring (computed, not raw API)
    score_breakdown: ScoreBreakdown
    risk_tier: str                 # "low" | "medium" | "high" | "speculative"

    # Metadata
    fetched_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    # Optional fields for protocol-specific data
    extra: dict = field(default_factory=dict)

    # ── Instrument type fields ──────────────────────────────────────────────
    opportunity_type: str = ""              # "LENDING" | "BORROWING" | "STAKING" | "LIQUIDITY" | "LEVERAGED" | "OPTIONS" | "STRUCTURED"
    yield_source: str = ""                  # "supply_interest" | "trading_fees" | "token_incentives" | "rebalancing" | "spread" | "options_premium"
    liquidity_profile: str = ""             # "INSTANT" | "INTERVAL" | "LOCKED" | "THETA_GATED"
    withdrawal_constraints: str = ""        # Human-readable string, e.g. "None", "7-day timelock"
    curator_or_strategy_manager: str = ""   # Who manages strategy, e.g. "Morpho Labs", "Aave Governance"
    reward_token_dependence: float = 0.0     # 0.0–1.0, how much yield depends on reward tokens
    stacking_risk: str = ""                 # "NONE" | "LOW" | "MEDIUM" | "HIGH"
    maturity_date: Optional[str] = None     # ISO date string, e.g. "2025-06-30" or None for open-ended

    @property
    def score(self) -> float:
        return self.score_breakdown.composite

    @property
    def apy_pct(self) -> float:
        """APY as percentage (3.8 instead of 0.038)."""
        return round(self.apy * 100, 4)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "protocol": self.protocol,
            "protocol_display": self.protocol_display,
            "chain": self.chain,
            "asset": self.asset,
            "pool_id": self.pool_id,
            "pool_meta": self.pool_meta,
            "apy": self.apy,
            "apy_pct": self.apy_pct,
            "reward_mix": self.reward_mix.to_dict(),
            "tvl_usd": self.tvl_usd,
            "source": self.source,
            "source_confidence": self.source_confidence,
            "url": self.url,
            "score": self.score,
            "score_breakdown": self.score_breakdown.to_dict(),
            "risk_tier": self.risk_tier,
            "fetched_at": self.fetched_at,
            "extra": self.extra,
            # Instrument type fields
            "opportunity_type": self.opportunity_type,
            "yield_source": self.yield_source,
            "liquidity_profile": self.liquidity_profile,
            "withdrawal_constraints": self.withdrawal_constraints,
            "curator_or_strategy_manager": self.curator_or_strategy_manager,
            "reward_token_dependence": self.reward_token_dependence,
            "stacking_risk": self.stacking_risk,
            "maturity_date": self.maturity_date,
        }
