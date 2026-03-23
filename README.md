# Yield Claw

Risk-adjusted stablecoin yield dashboard with normalized opportunity scoring.

## How to Run

See **START.md** for full instructions.

```bash
cd yield-claw
pip3 install -r requirements.txt
python3 app.py
# → open http://localhost:5001
```

## What Phase 2 Does

- Live data from DefiLlama, Morpho Blue, Kamino (Solana)
- Instrument-type scoring (LENDING / VAULT / LST / FIXED_TERM)
- 8-field opportunity schema with curator/risk/sustainability data
- Multi-source pooling and deduplication
- 139 tests passing

## What Phase 1 Does NOT Do

- No execution or capital movement
- No Morpho, Kamino, Solana (Phase 2)
- No Pendle PT (Phase 3)

## Running Tests

```bash
python3 -m pytest -q
```

## Versions

| Tag | Description |
|-----|-------------|
| v1 | Aave only, 77 tests |
| v2 | + Morpho Blue, Kamino Solana, instrument types, 139 tests |

## Data Sources

- DefiLlama (free, no auth)
- Morpho API (free, no auth)
- Kamino Finance API (free, no auth)
