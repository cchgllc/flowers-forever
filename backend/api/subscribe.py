"""
POST /api/subscribe
===================
Creates a Recurly account + subscription from the Recurly.js token.

The Recurly Python SDK v4 takes plain dicts for all request bodies —
there are no BillingInfoCreate / AccountCreate / SubscriptionCreate
classes in this version. Every body is just a dict matching the schema.
"""

import logging
import re
from datetime import datetime, timezone

import recurly.errors
from recurly.base_errors import ApiError as RecurlyApiError
from flask import Blueprint, jsonify, request

from utils.recurly_client import client
from utils.validators import validate_subscription_payload

logger = logging.getLogger(__name__)

subscribe_bp = Blueprint("subscribe", __name__)


def _extract_3ds_token(exc):
    """
    Extract three_d_secure_action_token_id from a Recurly SDK error.

    Recurly API v3 encodes the 3DS token inside the params list as:
      {"param": "three_d_secure_action_token_id", "message": "<token>"}
    i.e. the TOKEN VALUE is in the 'message' field of that param entry.
    """
    try:
        error_obj = getattr(exc, 'error', None)
        if not error_obj:
            return None

        error_type = getattr(error_obj, 'type', 'unknown')
        params      = getattr(error_obj, 'params', None) or []
        logger.info("3DS extraction — error.type=%s params=%s", error_type, params)

        # Path 1: direct attribute
        token = getattr(error_obj, 'three_d_secure_action_token_id', None)
        if token:
            return token

        # Path 2: params list — token value is in entry["message"] where
        #          entry["param"] == "three_d_secure_action_token_id"
        for param in params:
            if isinstance(param, dict):
                if param.get('param') == 'three_d_secure_action_token_id':
                    token = param.get('message')
                    if token:
                        return token
            else:
                if getattr(param, 'param', None) == 'three_d_secure_action_token_id':
                    token = getattr(param, 'message', None)
                    if token:
                        return token

    except Exception:
        logger.exception("Error while extracting 3DS token")

    return None


def _account_code_from_email(email: str) -> str:
    """Derive a stable, URL-safe Recurly account code from an email address."""
    safe = re.sub(r"[^a-z0-9._-]", "-", email.lower())
    return safe[:50]


@subscribe_bp.post("/subscribe")
def create_subscription():
    """
    Expected JSON body (mirrors collectFormData() in js/checkout.js):
    {
        "recurly_token": "9ce4c22f-...",
        "plan_code":     "classic-monthly",
        "first_name":    "Jane",
        "last_name":     "Smith",
        "email":         "jane@example.com",
        "phone":         "5551234567",
        "address": {
            "address1": "123 Bloom St",
            "address2": "Apt 4B",
            "city":     "New York",
            "state":    "NY",
            "zip":      "10001",
            "country":  "US"
        },
        "coupon_code":  "FOREVER20",
        "start_date":   "asap" | "YYYY-MM-DD",
        "occasion":     "home",
        "color_prefs":  ["warm", "pastel"]
    }
    """
    if client is None:
        return jsonify({
            "success": False,
            "message": "Recurly API key not configured. See .env.example.",
        }), 503

    data = request.get_json(silent=True)
    if data is None:
        return jsonify({"success": False, "message": "Request body must be JSON."}), 400

    # --- Validate ---
    errors = validate_subscription_payload(data)
    if errors:
        return jsonify({"success": False, "message": errors[0], "errors": errors}), 422

    address = data["address"]

    # --- Build the subscription body as a plain dict ---
    subscription_body = {
        "plan_code": data["plan_code"],
        "currency": "USD",
        "account": {
            "code": _account_code_from_email(data["email"]),
            "first_name": data["first_name"].strip(),
            "last_name":  data["last_name"].strip(),
            "email":      data["email"].strip().lower(),
            "address": {
                "street1":     address["address1"],
                "street2":     address.get("address2") or None,
                "city":        address["city"],
                "region":      address["state"].upper(),
                "postal_code": address["zip"],
                "country":     address.get("country", "US"),
                "phone":       data.get("phone") or None,
            },
            "billing_info": {
                "token_id": data["recurly_token"],
            },
        },
    }

    # 3D Secure: attach action result token when the frontend sends one
    # (second call after the customer completes the bank challenge UI)
    tds_result = data.get("three_d_secure_action_result_token_id")
    if tds_result:
        subscription_body["account"]["billing_info"][
            "three_d_secure_action_result_token_id"
        ] = tds_result

    # Optional: specific start date
    start_date = data.get("start_date", "asap")
    if start_date and start_date != "asap":
        try:
            dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
            subscription_body["starts_at"] = dt.isoformat()
        except ValueError:
            logger.warning("Invalid start_date '%s', defaulting to immediate.", start_date)

    # Optional: coupon code
    coupon_code = data.get("coupon_code")
    if coupon_code:
        subscription_body["coupon_codes"] = [coupon_code.strip()]

    # --- Call Recurly ---
    try:
        subscription = client.create_subscription(subscription_body)

        logger.info(
            "Subscription created: id=%s account=%s plan=%s",
            subscription.id,
            subscription.account.code,
            data["plan_code"],
        )

        return jsonify({
            "success": True,
            "subscription_id": subscription.id,
            "account_code":    subscription.account.code,
            "state":           subscription.state,
            "current_period_ends_at": (
                subscription.current_period_ends_at.isoformat()
                if subscription.current_period_ends_at else None
            ),
        }), 201

    except (recurly.errors.ValidationError, recurly.errors.TransactionError) as e:
        tds_token = _extract_3ds_token(e)
        if tds_token:
            logger.info("3DS required — returning action token to frontend")
            return jsonify({
                "success": False,
                "three_d_secure_action_token_id": tds_token,
                "message": "Card authentication required.",
            }), 402
        status = 422 if isinstance(e, recurly.errors.ValidationError) else 402
        logger.warning("Recurly %s: %s", type(e).__name__, e)
        return jsonify({"success": False, "message": str(e)}), status

    except recurly.errors.NotFoundError as e:
        logger.warning("Recurly NotFoundError (bad plan/coupon?): %s", e)
        return jsonify({"success": False, "message": str(e)}), 404

    except recurly.errors.InvalidTokenError as e:
        logger.warning("Recurly InvalidTokenError (bad Recurly.js token): %s", e)
        return jsonify({
            "success": False,
            "message": "Payment token is invalid or expired. Please re-enter your card details.",
        }), 422

    except RecurlyApiError as e:
        logger.error("Recurly API error: %s", e, exc_info=True)
        return jsonify({"success": False, "message": "A payment error occurred. Please try again."}), 502

    except Exception as e:
        logger.error("Unexpected error in create_subscription: %s", e, exc_info=True)
        return jsonify({"success": False, "message": "Internal server error."}), 500
