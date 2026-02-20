"""
Vercel Serverless Function: POST /api/subscribe
Creates a Recurly account + subscription from the Recurly.js token.
"""

import json
import logging
import os
import re
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler

import recurly
import recurly.errors
from recurly.base_errors import ApiError as RecurlyApiError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VALID_PLAN_CODES = {
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
}

US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA",
    "HI","ID","IL","IN","IA","KS","KY","LA","ME","MD",
    "MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC",
    "SD","TN","TX","UT","VT","VA","WA","WV","WI","WY",
}


def _get_client():
    api_key = os.environ.get("RECURLY_PRIVATE_API_KEY", "")
    if not api_key:
        return None
    return recurly.Client(api_key)


def _account_code_from_email(email: str) -> str:
    safe = re.sub(r"[^a-z0-9._-]", "-", email.lower())
    return safe[:50]


def _validate(data):
    errors = []
    for key in ("recurly_token", "plan_code", "first_name", "last_name", "email"):
        if not isinstance(data.get(key, ""), str) or not data.get(key, "").strip():
            errors.append(f"'{key}' is required.")
    email = data.get("email", "")
    if email and not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        errors.append("'email' is not a valid email address.")
    plan_code = data.get("plan_code", "")
    if plan_code and plan_code not in VALID_PLAN_CODES:
        errors.append(f"'plan_code' '{plan_code}' is not a recognised plan.")
    address = data.get("address")
    if not isinstance(address, dict):
        errors.append("'address' must be an object.")
    else:
        for key in ("address1", "city", "state", "zip"):
            if not isinstance(address.get(key, ""), str) or not address.get(key, "").strip():
                errors.append(f"'address.{key}' is required.")
        state = address.get("state", "")
        if state and state.upper() not in US_STATES:
            errors.append(f"'address.state' '{state}' is not a valid US state.")
        zip_code = address.get("zip", "")
        if zip_code and not re.match(r"^\d{5}$", str(zip_code)):
            errors.append("'address.zip' must be a 5-digit US ZIP code.")
    return errors


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


class handler(BaseHTTPRequestHandler):

    def do_OPTIONS(self):
        self.send_response(204)
        for k, v in _cors_headers().items():
            self.send_header(k, v)
        self.end_headers()

    def do_POST(self):
        client = _get_client()
        if client is None:
            return _respond(self, 503, {"success": False, "message": "Recurly API key not configured."})

        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length)
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return _respond(self, 400, {"success": False, "message": "Request body must be JSON."})

        errors = _validate(data)
        if errors:
            return _respond(self, 422, {"success": False, "message": errors[0], "errors": errors})

        address = data["address"]
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

        start_date = data.get("start_date", "asap")
        if start_date and start_date != "asap":
            try:
                dt = datetime.strptime(start_date, "%Y-%m-%d").replace(tzinfo=timezone.utc)
                subscription_body["starts_at"] = dt.isoformat()
            except ValueError:
                pass

        coupon_code = data.get("coupon_code")
        if coupon_code:
            subscription_body["coupon_codes"] = [coupon_code.strip().upper()]

        try:
            subscription = client.create_subscription(subscription_body)
            logger.info("Subscription created: id=%s plan=%s", subscription.id, data["plan_code"])
            return _respond(self, 201, {
                "success": True,
                "subscription_id": subscription.id,
                "account_code":    subscription.account.code,
                "state":           subscription.state,
                "current_period_ends_at": (
                    subscription.current_period_ends_at.isoformat()
                    if subscription.current_period_ends_at else None
                ),
            })

        except recurly.errors.ValidationError as e:
            return _respond(self, 422, {"success": False, "message": str(e)})
        except recurly.errors.NotFoundError as e:
            return _respond(self, 404, {"success": False, "message": str(e)})
        except recurly.errors.TransactionError as e:
            return _respond(self, 402, {"success": False, "message": str(e)})
        except recurly.errors.InvalidTokenError:
            return _respond(self, 422, {"success": False,
                "message": "Payment token is invalid or expired. Please re-enter your card details."})
        except RecurlyApiError as e:
            logger.error("Recurly API error: %s", e)
            return _respond(self, 502, {"success": False, "message": "A payment error occurred. Please try again."})
        except Exception as e:
            logger.error("Unexpected error: %s", e, exc_info=True)
            return _respond(self, 500, {"success": False, "message": "Internal server error."})

    def log_message(self, format, *args):
        logger.info("%s - %s", self.address_string(), format % args)
