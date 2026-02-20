"""
POST /api/webhooks/recurly
==========================
Receives and processes Recurly push notifications (webhooks).

Recurly sends an XML POST to this endpoint for every subscription
lifecycle event. We parse the XML, verify the request came from Recurly
via HTTP Basic Auth, and dispatch to the appropriate handler.

Setup in Recurly Admin Console:
  Configuration → Notifications → Add Endpoint
  URL: https://yourdomain.com/api/webhooks/recurly
  Username: recurly   (or any string — set RECURLY_WEBHOOK_USER in .env)
  Password: <strong random string — set RECURLY_WEBHOOK_SECRET in .env>

Supported events handled here:
  - new_subscription_notification
  - updated_subscription_notification
  - canceled_subscription_notification
  - expired_subscription_notification
  - renewed_subscription_notification
  - reactivated_subscription_notification
  - billing_info_updated_notification
  - failed_payment_notification
  - successful_payment_notification
  - new_invoice_notification
"""

import hashlib
import hmac
import logging
import os
import xml.etree.ElementTree as ET
from functools import wraps

from flask import Blueprint, jsonify, request

logger = logging.getLogger(__name__)

webhooks_bp = Blueprint("webhooks", __name__)

# -----------------------------------------------------------------------
# Auth helpers
# -----------------------------------------------------------------------

def _check_basic_auth(f):
    """Decorator: verify HTTP Basic Auth credentials on the webhook endpoint."""
    @wraps(f)
    def wrapper(*args, **kwargs):
        expected_user   = os.environ.get("RECURLY_WEBHOOK_USER", "recurly")
        expected_secret = os.environ.get("RECURLY_WEBHOOK_SECRET", "")

        if not expected_secret:
            # No secret configured — skip auth in development only
            if os.environ.get("FLASK_ENV") == "development":
                logger.warning("RECURLY_WEBHOOK_SECRET not set — skipping auth (dev mode).")
                return f(*args, **kwargs)
            return jsonify({"error": "Webhook auth not configured"}), 503

        auth = request.authorization
        if not auth:
            return ("Unauthorized", 401, {"WWW-Authenticate": 'Basic realm="Recurly"'})

        # Constant-time comparison to avoid timing attacks
        user_ok   = hmac.compare_digest(auth.username or "", expected_user)
        secret_ok = hmac.compare_digest(auth.password or "", expected_secret)

        if not (user_ok and secret_ok):
            logger.warning("Webhook auth failure from %s", request.remote_addr)
            return ("Forbidden", 403)

        return f(*args, **kwargs)
    return wrapper


# -----------------------------------------------------------------------
# XML parsing helpers
# -----------------------------------------------------------------------

def _text(node, *path: str, default: str = "") -> str:
    """Safely extract text from a nested XML path."""
    current = node
    for tag in path:
        if current is None:
            return default
        current = current.find(tag)
    if current is None or current.text is None:
        return default
    return current.text.strip()


def _parse_payload(xml_body: bytes) -> tuple[str, ET.Element]:
    """
    Parse a Recurly webhook XML body.
    Returns (event_type, root_element).
    The root tag IS the event type, e.g. 'new_subscription_notification'.
    """
    root = ET.fromstring(xml_body)
    return root.tag, root


# -----------------------------------------------------------------------
# Event handlers
# -----------------------------------------------------------------------

def _handle_new_subscription(root: ET.Element) -> None:
    account_code = _text(root, "account", "account_code")
    email        = _text(root, "account", "email")
    plan_code    = _text(root, "subscription", "plan", "plan_code")
    sub_uuid     = _text(root, "subscription", "uuid")

    logger.info(
        "NEW SUBSCRIPTION: account=%s email=%s plan=%s sub=%s",
        account_code, email, plan_code, sub_uuid,
    )
    # TODO: send welcome email, provision delivery schedule, etc.


def _handle_canceled_subscription(root: ET.Element) -> None:
    account_code = _text(root, "account", "account_code")
    sub_uuid     = _text(root, "subscription", "uuid")
    expires_at   = _text(root, "subscription", "expires_at")

    logger.info(
        "CANCELED SUBSCRIPTION: account=%s sub=%s expires=%s",
        account_code, sub_uuid, expires_at,
    )
    # TODO: send cancellation confirmation email, schedule offboarding


def _handle_updated_subscription(root: ET.Element) -> None:
    account_code = _text(root, "account", "account_code")
    new_plan     = _text(root, "subscription", "plan", "plan_code")
    sub_uuid     = _text(root, "subscription", "uuid")

    logger.info(
        "UPDATED SUBSCRIPTION: account=%s sub=%s new_plan=%s",
        account_code, sub_uuid, new_plan,
    )
    # TODO: update internal plan tracking, send confirmation email


def _handle_expired_subscription(root: ET.Element) -> None:
    account_code = _text(root, "account", "account_code")
    sub_uuid     = _text(root, "subscription", "uuid")

    logger.info("EXPIRED SUBSCRIPTION: account=%s sub=%s", account_code, sub_uuid)
    # TODO: trigger win-back email campaign


def _handle_renewed_subscription(root: ET.Element) -> None:
    account_code = _text(root, "account", "account_code")
    sub_uuid     = _text(root, "subscription", "uuid")
    next_renewal = _text(root, "subscription", "current_period_ends_at")

    logger.info(
        "RENEWED SUBSCRIPTION: account=%s sub=%s next=%s",
        account_code, sub_uuid, next_renewal,
    )
    # TODO: send "your next bouquet is on its way" email


def _handle_reactivated_subscription(root: ET.Element) -> None:
    account_code = _text(root, "account", "account_code")
    sub_uuid     = _text(root, "subscription", "uuid")

    logger.info("REACTIVATED SUBSCRIPTION: account=%s sub=%s", account_code, sub_uuid)
    # TODO: send welcome-back email


def _handle_billing_info_updated(root: ET.Element) -> None:
    account_code = _text(root, "account", "account_code")
    email        = _text(root, "account", "email")

    logger.info("BILLING INFO UPDATED: account=%s email=%s", account_code, email)
    # TODO: send payment method updated confirmation email


def _handle_failed_payment(root: ET.Element) -> None:
    account_code   = _text(root, "account", "account_code")
    email          = _text(root, "account", "email")
    invoice_number = _text(root, "invoice", "invoice_number")
    amount_due     = _text(root, "invoice", "balance_in_cents")
    error_msg      = _text(root, "transaction", "message")

    logger.warning(
        "FAILED PAYMENT: account=%s email=%s invoice=%s amount_cents=%s error=%s",
        account_code, email, invoice_number, amount_due, error_msg,
    )
    # TODO: send payment failure email with retry link


def _handle_successful_payment(root: ET.Element) -> None:
    account_code   = _text(root, "account", "account_code")
    invoice_number = _text(root, "invoice", "invoice_number")
    amount_cents   = _text(root, "transaction", "amount_in_cents")

    logger.info(
        "SUCCESSFUL PAYMENT: account=%s invoice=%s amount_cents=%s",
        account_code, invoice_number, amount_cents,
    )
    # TODO: store payment record, trigger shipment if applicable


def _handle_new_invoice(root: ET.Element) -> None:
    account_code   = _text(root, "account", "account_code")
    invoice_number = _text(root, "invoice", "invoice_number")
    state          = _text(root, "invoice", "state")

    logger.info(
        "NEW INVOICE: account=%s invoice=%s state=%s",
        account_code, invoice_number, state,
    )
    # TODO: store invoice reference


# -----------------------------------------------------------------------
# Dispatcher
# -----------------------------------------------------------------------

_HANDLERS = {
    "new_subscription_notification":          _handle_new_subscription,
    "updated_subscription_notification":      _handle_updated_subscription,
    "canceled_subscription_notification":     _handle_canceled_subscription,
    "expired_subscription_notification":      _handle_expired_subscription,
    "renewed_subscription_notification":      _handle_renewed_subscription,
    "reactivated_subscription_notification":  _handle_reactivated_subscription,
    "billing_info_updated_notification":      _handle_billing_info_updated,
    "failed_payment_notification":            _handle_failed_payment,
    "successful_payment_notification":        _handle_successful_payment,
    "new_invoice_notification":               _handle_new_invoice,
}


# -----------------------------------------------------------------------
# Endpoint
# -----------------------------------------------------------------------

@webhooks_bp.post("/webhooks/recurly")
@_check_basic_auth
def recurly_webhook():
    xml_body = request.get_data()
    if not xml_body:
        return jsonify({"error": "Empty body"}), 400

    try:
        event_type, root = _parse_payload(xml_body)
    except ET.ParseError as e:
        logger.error("Failed to parse webhook XML: %s", e)
        return jsonify({"error": "Invalid XML"}), 400

    handler = _HANDLERS.get(event_type)
    if handler:
        try:
            handler(root)
        except Exception as e:
            # Log the error but always return 200 — otherwise Recurly will
            # keep retrying and clog the queue.
            logger.error("Error in webhook handler for '%s': %s", event_type, e, exc_info=True)
    else:
        logger.debug("Unhandled webhook event: %s", event_type)

    # Recurly expects a 2xx response to acknowledge receipt.
    return ("", 200)
