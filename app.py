"""
Yield Claw — Flask backend.

Endpoints:
  GET /                      → dashboard HTML
  GET /api/opportunities     → normalized opportunity objects (JSON)
  GET /api/opportunities/aave → Aave-only subset
  GET /api/health            → status + cache info
"""

import os
import time
import logging
from datetime import datetime, timezone
from flask import Flask, jsonify, render_template, request
from flask_caching import Cache

from data.defillama import fetch_all_opportunities, fetch_aave_opportunities, fetch_risk_free_rate

# ──────────────────────────────────────────────
# App setup
# ──────────────────────────────────────────────

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(__name__)

app = Flask(__name__)

# Simple in-memory cache, 60s TTL
app.config["CACHE_TYPE"] = "SimpleCache"
app.config["CACHE_DEFAULT_TIMEOUT"] = 60
cache = Cache(app)

# ──────────────────────────────────────────────
# State
# ──────────────────────────────────────────────

_last_fetch_at: str = None
_last_error: str = None


# ──────────────────────────────────────────────
# Routes
# ──────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/opportunities")
@cache.cached(timeout=60)
def get_opportunities():
    global _last_fetch_at, _last_error
    try:
        risk_free_rate = fetch_risk_free_rate()
        opportunities = fetch_all_opportunities(risk_free_rate=risk_free_rate)
        _last_fetch_at = datetime.now(timezone.utc).isoformat()
        _last_error = None
        log.info(f"Fetched {len(opportunities)} opportunities")
        return jsonify({
            "ok": True,
            "count": len(opportunities),
            "risk_free_rate": risk_free_rate,
            "risk_free_rate_pct": round(risk_free_rate * 100, 4),
            "fetched_at": _last_fetch_at,
            "opportunities": [o.to_dict() for o in opportunities],
        })
    except Exception as e:
        _last_error = str(e)
        log.error(f"Error fetching opportunities: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/opportunities/aave")
@cache.cached(timeout=60)
def get_aave_opportunities():
    global _last_fetch_at, _last_error
    try:
        chains_param = request.args.get("chains")
        chains = chains_param.split(",") if chains_param else None

        risk_free_rate = fetch_risk_free_rate()
        opportunities = fetch_aave_opportunities(chains=chains, risk_free_rate=risk_free_rate)
        _last_fetch_at = datetime.now(timezone.utc).isoformat()
        _last_error = None
        log.info(f"Fetched {len(opportunities)} Aave opportunities")
        return jsonify({
            "ok": True,
            "count": len(opportunities),
            "risk_free_rate": risk_free_rate,
            "risk_free_rate_pct": round(risk_free_rate * 100, 4),
            "fetched_at": _last_fetch_at,
            "opportunities": [o.to_dict() for o in opportunities],
        })
    except Exception as e:
        _last_error = str(e)
        log.error(f"Error fetching Aave opportunities: {e}")
        return jsonify({"ok": False, "error": str(e)}), 500


@app.route("/api/health")
def health():
    return jsonify({
        "ok": True,
        "service": "yield-claw",
        "last_fetch_at": _last_fetch_at,
        "last_error": _last_error,
        "cache_ttl_seconds": 60,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    })


# ──────────────────────────────────────────────
# Dev runner
# ──────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5001))
    debug = os.environ.get("DEBUG", "true").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
