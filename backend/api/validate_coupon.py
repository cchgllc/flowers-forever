"""
POST /api/validate_coupon
=========================
Looks up a Recurly coupon by code and returns its discount details
so the frontend can display the correct amount in the order summary.
"""

import logging

import recurly
import recurly.errors
from flask import Blueprint, jsonify, request

from ..utils.recurly_client import get_client

logger = logging.getLogger(__name__)

validate_coupon_bp = Blueprint("validate_coupon", __name__)


def _parse_discount(coupon):
    """
    Returns a serialisable dict describing the coupon discount.

    Recurly discount types:
      percent    — discount.percent (integer, e.g. 20 for 20%)
      fixed      — discount.currencies list [{currency, amount}]
      free_trial — no monetary preview; returns type only
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


@validate_coupon_bp.post("/validate_coupon")
def validate_coupon():
    data = request.get_json(silent=True) or {}
    coupon_code = (data.get("coupon_code") or "").strip()

    if not coupon_code:
        return jsonify({"valid": False, "message": "coupon_code is required."}), 400

    client = get_client()
    if client is None:
        return jsonify({"valid": False, "message": "Recurly API key not configured."}), 503

    try:
        coupon = client.get_coupon(coupon_code)

        state = getattr(coupon, "state", None)
        if state not in ("redeemable",):
            return jsonify({"valid": False, "message": f"This coupon is {state} and cannot be applied."})

        discount = _parse_discount(coupon)
        return jsonify({
            "valid": True,
            "coupon_code": coupon_code,
            "name": getattr(coupon, "name", coupon_code),
            "discount": discount,
        })

    except recurly.errors.NotFoundError:
        # May be a bulk/unique coupon sub-code — accept optimistically and
        # let Recurly validate it when the subscription is created.
        logger.info("Coupon %s not found via get_coupon — accepting as unique/bulk code", coupon_code)
        return jsonify({
            "valid": True,
            "coupon_code": coupon_code,
            "name": "Promo code",
            "discount": None,
        })

    except Exception:
        logger.exception("Error looking up coupon %s", coupon_code)
        return jsonify({"valid": False, "message": "Could not validate coupon. Please try again."}), 502
