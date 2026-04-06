"""
Vercel Serverless Function: POST /api/validate_coupon
Looks up a Recurly coupon and returns its discount details.
"""

import json
import logging
import os
from http.server import BaseHTTPRequestHandler

import recurly
import recurly.errors

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _get_client():
    api_key = os.environ.get("RECURLY_PRIVATE_API_KEY", "")
    if not api_key:
        return None
    return recurly.Client(api_key)


def _cors_headers():
    return {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "POST, OPTIONS",
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


def _parse_discount(coupon):
    """
    Returns a dict describing the coupon discount so the frontend
    can display the correct amount in the order summary.

    Recurly discount types:
      percent   — coupon.discount.percent (integer, e.g. 20 for 20%)
      fixed     — coupon.discount.currencies list [{currency, amount}]
      free_trial — n/a for billing, skip preview
    """
    discount = coupon.discount
    if discount is None:
        return None

    dtype = getattr(discount, "type", None)

    if dtype == "percent":
        return {
            "type": "percent",
            "percent": getattr(discount, "percent", 0),
        }

    if dtype == "fixed":
        currencies = getattr(discount, "currencies", []) or []
        usd = next(
            (c for c in currencies if getattr(c, "currency", "") == "USD"),
            currencies[0] if currencies else None,
        )
        if usd:
            return {
                "type": "fixed",
                "amount": float(getattr(usd, "amount", 0)),
            }

    return {"type": dtype}


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in _cors_headers().items():
            self.send_header(k, v)
        self.end_headers()

    def do_POST(self):
        client = _get_client()
        if client is None:
            return _respond(self, 503, {"valid": False, "message": "Recurly API key not configured."})

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return _respond(self, 400, {"valid": False, "message": "Request body must be JSON."})

        coupon_code = (data.get("coupon_code") or "").strip()
        if not coupon_code:
            return _respond(self, 400, {"valid": False, "message": "coupon_code is required."})

        try:
            coupon = client.get_coupon(coupon_code)

            # Reject expired or maxed-out coupons found via get_coupon
            state = getattr(coupon, "state", None)
            if state not in ("redeemable",):
                return _respond(self, 200, {"valid": False, "message": f"This coupon is {state} and cannot be applied."})

            discount = _parse_discount(coupon)
            return _respond(self, 200, {
                "valid": True,
                "coupon_code": coupon_code,
                "name": getattr(coupon, "name", coupon_code),
                "discount": discount,
            })

        except recurly.errors.NotFoundError:
            # Code not found as a standard coupon — it may be a bulk/unique
            # coupon sub-code. Accept it optimistically and let Recurly
            # validate the code when the subscription is created.
            logger.info("Coupon %s not found via get_coupon — accepting as unique/bulk code", coupon_code)
            return _respond(self, 200, {
                "valid": True,
                "coupon_code": coupon_code,
                "name": "Promo code",
                "discount": None,
            })

        except Exception:
            logger.exception("Error looking up coupon %s", coupon_code)
            return _respond(self, 502, {"valid": False, "message": "Could not validate coupon. Please try again."})
