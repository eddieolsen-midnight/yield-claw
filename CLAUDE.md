# Yield Claw — CLAUDE.md

You are building **Yield Claw** — a yield intelligence dashboard for Eddie's treasury management.

## Rules

1. **Normalize ALL data to the opportunity object schema** before adding to UI. No raw API responses in the frontend.
2. **Protocol-native data > aggregator data.** DefiLlama is L1, protocol APIs are L2.
3. **Never show APY without also showing `reward_mix` and `source_confidence`.**
4. **Compounding logic: threshold-based only, never time-based.**
5. **Pendle positions: label as "PT implied yield", NOT "fixed yield".**
6. **Morpho vaults: treat as ERC-4626 allocator structures, NOT plain lending.**
7. **Tests required before every commit.**
8. **No feature creep: finish Aave card before starting Morpho.**
9. **Build order: data schema → Flask endpoint → Aave card → Morpho → Pendle.**

## Project Brief

See `BRIEF FOR_WAYNE.md` in the parent directory for the full spec.

## Quick Ref

- Dashboard: Flask + HTML/JS, auto-refresh 60s
- Primary data: DefiLlama API (free, no auth)
- Scoring: 6 sub-scores → weighted composite
- Opportunity schema: see BRIEF_FOR_WAYNE.md

## When Done

Run: `openclaw system event --text "Yield Claw: [brief summary of what was built]" --mode now`
