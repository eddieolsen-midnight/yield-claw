# Yield Claw

Bloomberg for onchain yield allocation. Yield Claw is a Flask-based dashboard that aggregates DeFi lending rates from DefiLlama's public API, normalizes them into a structured opportunity schema, and scores them by risk-adjusted return to surface the best stablecoin yield routes for treasury management.

## How to Run

```bash
pip install -r requirements.txt
python3 app.py
```

Then open `http://localhost:5001` in your browser.

## Current Scope (Phase 1)

- **Flask dashboard** with auto-refresh every 60 seconds
- **DefiLlama API** as the sole data source (free, no auth required)
- **Normalized opportunity objects** — all protocol data is transformed to a standard schema before reaching the UI
- **6-axis scoring model** for risk-adjusted yield comparison
- **77 passing tests** covering schema validation, scoring logic, and data client behavior

## Data Source

DefiLlama API (`https://api.llama.fi/lendings`) — no API key required.

## What Phase 1 Does NOT Do

- No trade execution or wallet integration
- No Morpho Blue support
- No Pendle PT/SY mechanics
- No auth, database, or persistence layer

These are Phase 2+.

## Testing

```bash
pytest
```

## Screenshot

![Dashboard](./screenshots/dashboard.png)

> Add a screenshot to `screenshots/dashboard.png` to see it here.
