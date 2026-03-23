# Yield Claw — CLAUDE.md

You are building **Yield Claw** — a yield intelligence dashboard for Eddie's treasury management.

## Hard Rules (Phase 1 Freeze)

1. **Normalize ALL data to the opportunity object schema before adding to UI.** No raw API responses in templates or API responses.
2. **No raw API objects in templates.** All data must pass through the normalization layer first.
3. **Tests required for schema/scoring/data clients before every commit.** Do not skip tests.
4. **No execution layer.** No wallet integration, no transaction signing, no on-chain writes.
5. **No Morpho or Pendle.** Phase 1 scope is DefiLlama + Aave only.
6. **No auth or database.** Unless explicitly approved by Winston.
7. **Phase 1 is frozen.** Do not add new features. Focus is cleanup, documentation, and push.

## Scoring Model

6 sub-scores → weighted composite:
- `apy_score` — raw yield strength
- `stability_score` — TVL and protocol age
- `liquidity_score` — 24h volume and spread
- `risk_score` — audit status and hack history
- `complexity_score` — token mechanics and lockup
- `implied_rewards_score` — native token incentives

## Opportunity Schema

```
{
  "protocol": str,
  "symbol": str,
  "apy": float,
  "apy_base": float,
  "apy_reward": float,
  "reward_mix": float,        # 0.0 = pure base, 1.0 = pure reward
  "source_confidence": float,  # 0.0–1.0
  "tvls": dict,
  "mu": float,
  "sigma": float,
  "count": int,
  "legnth": int,
  "apy_potential": float,
  "stablecoin": bool,
  "rew_token": str | None,
  "rew_token_price": float,
  "total_borrow": float,
  "total_supply": float,
  "borrow_only": bool,
}
```

## Build Order

1. Data schema
2. Flask endpoint
3. Aave card
4. Morpho (Phase 2)
5. Pendle (Phase 3)

## When Done

Run: `openclaw system event --text "Yield Claw: [brief summary of what was built]" --mode now`

## Next Step

Phase 2 planning — not feature creep.
