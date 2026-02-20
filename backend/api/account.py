"""
Account & Subscription Management Endpoints
============================================
All Recurly SDK v4 calls use plain dicts as request bodies.
No recurly.BillingInfoCreate / SubscriptionPause / etc. classes exist
in this version of the library.
"""

import logging

import recurly.errors
from recurly.base_errors import ApiError as RecurlyApiError
from flask import Blueprint, jsonify, request

from utils.recurly_client import client

logger = logging.getLogger(__name__)

account_bp = Blueprint("account", __name__)


# -----------------------------------------------------------------------
# Auth stub — replace with real session / JWT verification
# -----------------------------------------------------------------------

def _auth_required(f):
    from functools import wraps

    @wraps(f)
    def wrapper(*args, **kwargs):
        # TODO: verify Bearer JWT or session cookie and confirm the caller
        # owns the requested account_code before proceeding.
        return f(*args, **kwargs)

    return wrapper


# -----------------------------------------------------------------------
# Serialisers
# -----------------------------------------------------------------------

def _serialize_subscription(sub) -> dict:
    return {
        "id":    sub.id,
        "uuid":  sub.uuid,
        "state": sub.state,
        "plan_code": sub.plan.code if sub.plan else None,
        "plan_name": sub.plan.name if sub.plan else None,
        "unit_amount": sub.unit_amount,
        "currency":    sub.currency,
        "current_period_started_at": (
            sub.current_period_started_at.isoformat()
            if sub.current_period_started_at else None
        ),
        "current_period_ends_at": (
            sub.current_period_ends_at.isoformat()
            if sub.current_period_ends_at else None
        ),
        "activated_at": sub.activated_at.isoformat() if sub.activated_at else None,
        "expires_at":   sub.expires_at.isoformat()   if sub.expires_at   else None,
        "paused_at":    sub.paused_at.isoformat()    if sub.paused_at    else None,
    }


def _serialize_invoice(inv) -> dict:
    return {
        "id":       inv.id,
        "number":   inv.number,
        "state":    inv.state,
        "total":    inv.total,
        "currency": inv.currency,
        "due_on":   inv.due_on.isoformat()   if inv.due_on   else None,
        "closed_at": inv.closed_at.isoformat() if inv.closed_at else None,
    }


def _get_active_subscription(account_code: str):
    """Return the first active subscription for an account, or None."""
    subs = client.list_account_subscriptions(
        f"code-{account_code}",
        params={"state": "active", "limit": 1},
    )
    for sub in subs.items():
        return sub
    return None


# -----------------------------------------------------------------------
# GET /api/account/<account_code>
# -----------------------------------------------------------------------

@account_bp.get("/account/<account_code>")
@_auth_required
def get_account(account_code: str):
    if client is None:
        return jsonify({"success": False, "message": "Recurly not configured"}), 503
    try:
        account    = client.get_account(f"code-{account_code}")
        active_sub = _get_active_subscription(account_code)
        return jsonify({
            "success": True,
            "account": {
                "code":       account.code,
                "email":      account.email,
                "first_name": account.first_name,
                "last_name":  account.last_name,
                "created_at": account.created_at.isoformat() if account.created_at else None,
            },
            "active_subscription": _serialize_subscription(active_sub) if active_sub else None,
        })
    except recurly.errors.NotFoundError:
        return jsonify({"success": False, "message": "Account not found"}), 404
    except RecurlyApiError as e:
        logger.error("get_account error: %s", e)
        return jsonify({"success": False, "message": str(e)}), 502


# -----------------------------------------------------------------------
# GET /api/account/<account_code>/subscriptions
# -----------------------------------------------------------------------

@account_bp.get("/account/<account_code>/subscriptions")
@_auth_required
def list_subscriptions(account_code: str):
    if client is None:
        return jsonify({"success": False, "message": "Recurly not configured"}), 503
    try:
        subs = client.list_account_subscriptions(
            f"code-{account_code}", params={"limit": 20}
        )
        return jsonify({
            "success": True,
            "subscriptions": [_serialize_subscription(s) for s in subs.items()],
        })
    except recurly.errors.NotFoundError:
        return jsonify({"success": False, "message": "Account not found"}), 404
    except RecurlyApiError as e:
        logger.error("list_subscriptions error: %s", e)
        return jsonify({"success": False, "message": str(e)}), 502


# -----------------------------------------------------------------------
# POST /api/account/<account_code>/subscription/pause
# Body: { "remaining_pause_cycles": 1 }
# -----------------------------------------------------------------------

@account_bp.post("/account/<account_code>/subscription/pause")
@_auth_required
def pause_subscription(account_code: str):
    if client is None:
        return jsonify({"success": False, "message": "Recurly not configured"}), 503

    data   = request.get_json(silent=True) or {}
    cycles = int(data.get("remaining_pause_cycles", 1))

    try:
        active_sub = _get_active_subscription(account_code)
        if not active_sub:
            return jsonify({"success": False, "message": "No active subscription found"}), 404

        updated = client.pause_subscription(
            active_sub.id,
            {"remaining_pause_cycles": cycles},
        )
        logger.info("Paused subscription %s for %d cycle(s)", active_sub.id, cycles)
        return jsonify({
            "success": True,
            "message": f"Subscription paused for {cycles} billing cycle(s).",
            "subscription": _serialize_subscription(updated),
        })
    except recurly.errors.NotFoundError:
        return jsonify({"success": False, "message": "Subscription not found"}), 404
    except recurly.errors.ValidationError as e:
        return jsonify({"success": False, "message": str(e)}), 422
    except RecurlyApiError as e:
        logger.error("pause_subscription error: %s", e)
        return jsonify({"success": False, "message": str(e)}), 502


# -----------------------------------------------------------------------
# POST /api/account/<account_code>/subscription/cancel
# Body: { "at_end_of_billing_period": true }
# -----------------------------------------------------------------------

@account_bp.post("/account/<account_code>/subscription/cancel")
@_auth_required
def cancel_subscription(account_code: str):
    if client is None:
        return jsonify({"success": False, "message": "Recurly not configured"}), 503

    data          = request.get_json(silent=True) or {}
    at_period_end = data.get("at_end_of_billing_period", True)

    try:
        active_sub = _get_active_subscription(account_code)
        if not active_sub:
            return jsonify({"success": False, "message": "No active subscription found"}), 404

        if at_period_end:
            updated = client.cancel_subscription(active_sub.id)
        else:
            updated = client.terminate_subscription(
                active_sub.id, params={"refund": "none"}
            )

        logger.info("Canceled subscription %s (at_period_end=%s)", active_sub.id, at_period_end)
        msg = "Subscription canceled."
        if at_period_end:
            msg += " You'll continue to receive deliveries until the end of your billing period."
        return jsonify({
            "success": True,
            "message": msg,
            "subscription": _serialize_subscription(updated),
        })
    except recurly.errors.NotFoundError:
        return jsonify({"success": False, "message": "Subscription not found"}), 404
    except RecurlyApiError as e:
        logger.error("cancel_subscription error: %s", e)
        return jsonify({"success": False, "message": str(e)}), 502


# -----------------------------------------------------------------------
# PUT /api/account/<account_code>/subscription/plan
# Body: { "plan_code": "premium-monthly" }
# -----------------------------------------------------------------------

@account_bp.put("/account/<account_code>/subscription/plan")
@_auth_required
def change_plan(account_code: str):
    if client is None:
        return jsonify({"success": False, "message": "Recurly not configured"}), 503

    data          = request.get_json(silent=True) or {}
    new_plan_code = (data.get("plan_code") or "").strip()
    if not new_plan_code:
        return jsonify({"success": False, "message": "'plan_code' is required."}), 422

    try:
        active_sub = _get_active_subscription(account_code)
        if not active_sub:
            return jsonify({"success": False, "message": "No active subscription found"}), 404

        updated = client.update_subscription(
            active_sub.id,
            {"plan_code": new_plan_code},
        )
        logger.info("Changed plan for subscription %s → %s", active_sub.id, new_plan_code)
        return jsonify({
            "success": True,
            "message": f"Plan updated to {new_plan_code}.",
            "subscription": _serialize_subscription(updated),
        })
    except recurly.errors.NotFoundError:
        return jsonify({"success": False, "message": "Subscription or plan not found"}), 404
    except recurly.errors.ValidationError as e:
        return jsonify({"success": False, "message": str(e)}), 422
    except RecurlyApiError as e:
        logger.error("change_plan error: %s", e)
        return jsonify({"success": False, "message": str(e)}), 502


# -----------------------------------------------------------------------
# PUT /api/account/<account_code>/billing
# Body: { "recurly_token": "<new Recurly.js token>" }
# -----------------------------------------------------------------------

@account_bp.put("/account/<account_code>/billing")
@_auth_required
def update_billing(account_code: str):
    if client is None:
        return jsonify({"success": False, "message": "Recurly not configured"}), 503

    data  = request.get_json(silent=True) or {}
    token = (data.get("recurly_token") or "").strip()
    if not token:
        return jsonify({"success": False, "message": "'recurly_token' is required."}), 422

    try:
        client.update_billing_info(
            f"code-{account_code}",
            {"token_id": token},
        )
        logger.info("Billing info updated for account %s", account_code)
        return jsonify({"success": True, "message": "Payment method updated successfully."})
    except recurly.errors.NotFoundError:
        return jsonify({"success": False, "message": "Account not found"}), 404
    except recurly.errors.ValidationError as e:
        return jsonify({"success": False, "message": str(e)}), 422
    except recurly.errors.TransactionError as e:
        return jsonify({"success": False, "message": str(e)}), 402
    except RecurlyApiError as e:
        logger.error("update_billing error: %s", e)
        return jsonify({"success": False, "message": str(e)}), 502


# -----------------------------------------------------------------------
# GET /api/account/<account_code>/invoices
# -----------------------------------------------------------------------

@account_bp.get("/account/<account_code>/invoices")
@_auth_required
def list_invoices(account_code: str):
    if client is None:
        return jsonify({"success": False, "message": "Recurly not configured"}), 503
    try:
        invoices = client.list_account_invoices(
            f"code-{account_code}", params={"limit": 20}
        )
        return jsonify({
            "success": True,
            "invoices": [_serialize_invoice(inv) for inv in invoices.items()],
        })
    except recurly.errors.NotFoundError:
        return jsonify({"success": False, "message": "Account not found"}), 404
    except RecurlyApiError as e:
        logger.error("list_invoices error: %s", e)
        return jsonify({"success": False, "message": str(e)}), 502
