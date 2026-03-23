# How to Run the Dashboard

## Quick Start

```bash
cd ~/Desktop/Yield\ Claw\ -\ Claude\ \&\ Winston\ Collab/yield-claw
pip3 install -r requirements.txt
python3 app.py
```

Then open **http://localhost:5001** in your browser.

---

## Requirements

- Python 3.9+
- `pip3` (run `pip3 install --upgrade pip` if you get "command not found")
- No API keys needed — all data comes from free public APIs (DefiLlama, Morpho, Kamino)

---

## Troubleshooting

**"pip: command not found"** → use `pip3` instead of `pip`

**Port 5001 already in use** → kill the existing process:
```bash
lsof -ti:5001 | xargs kill -9
python3 app.py
```

**Module not found errors** → reinstall requirements:
```bash
pip3 install -r requirements.txt
```

**Dashboard shows no data** → the APIs may be temporarily down. Wait 30 seconds and refresh.

---

## Git Commands

Check current version:
```bash
cd ~/Desktop/Yield\ Claw\ -\ Claude\ \&\ Winston\ Collab/yield-claw
git log --oneline
```

Update to latest:
```bash
cd ~/Desktop/Yield\ Claw\ -\ Claude\ \&\ Winston\ Collab/yield-claw
git pull origin main
```

---

## Versions

- **v1** — Aave only, 77 tests
- **v2** — Aave + Morpho Blue + Kamino Solana, 139 tests, instrument-type schema
