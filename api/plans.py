"""
Vercel Serverless Function: GET /api/plans
Returns pricing for each plan code fetched live from Recurly.
"""

import json
import logging
import os
from http.server import BaseHTTPRequestHandler

import recurly
import recurly.errors

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Plan codes shown on the product page
PLAN_CODES = [
    "1399",
    "classic-monthly",
    "premium-monthly",
    "deluxe-monthly",
    "biweekly-delivery",
    "weekly-delivery",
    "roses-monthly",
    "tropical-monthly",
    "petsafe-monthly",
    "plants-monthly",
]


def _get_client():
    api_key = os.environ.get("RECURLY_PRIVATE_API_KEY", "")
    if not api_key:
        return None
    return recurly.Client(api_key)


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, OPTIONS",
        "Access-Control-Allow-Headers": "Content-Type",
        "Content-Type": "application/json",
    }


def _respond(handler, status, body):
    encoded = json.dumps(body).encode()
    handler.send_response(status)
    for k, v in _cors_headers().items():
        handler.send_header(k, v)
    handler.send_header("Content-Length", str(len(encoded)))
    handler.end_headers()
    handler.wfile.write(encoded)


def _usd_price(plan):
    """Extract the USD unit_amount from a Recurly plan's currencies list."""
    currencies = getattr(plan, "currencies", []) or []
    usd = next((c for c in currencies if getattr(c, "currency", "") == "USD"), None)
    if usd:
        return float(getattr(usd, "unit_amount", 0))
    return None


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in _cors_headers().items():
            self.send_header(k, v)
        self.end_headers()

    def do_GET(self):
        client = _get_client()
        if client is None:
            return _respond(self, 503, {"success": False, "message": "Recurly API key not configured."})

        plans = {}
        for code in PLAN_CODES:
            try:
                plan = client.get_plan(code)
                price = _usd_price(plan)
                if price is not None:
                    plans[code] = {
                        "code":  code,
                        "name":  getattr(plan, "name", code),
                        "price": price,
                    }
            except recurly.errors.NotFoundError:
                logger.info("Plan %s not found in Recurly — skipping", code)
            except Exception:
                logger.exception("Error fetching plan %s", code)

        return _respond(self, 200, {"success": True, "plans": plans})
