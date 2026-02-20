"""
Input validation helpers for API request payloads.
"""

import re
from typing import Any

# All valid plan codes defined in the Recurly Admin Console
VALID_PLAN_CODES = {
    "1399",              # Classic Bouquet — $50.00/month
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


def _required(data: dict, *keys: str) -> list[str]:
    """Return a list of error messages for any missing/blank required keys."""
    errors = []
    for key in keys:
        val = data.get(key, "")
        if not isinstance(val, str) or not val.strip():
            errors.append(f"'{key}' is required.")
    return errors


def validate_subscription_payload(data: Any) -> list[str]:
    """
    Validate the JSON body sent to POST /api/subscribe.
    Returns a list of human-readable error strings (empty = valid).
    """
    if not isinstance(data, dict):
        return ["Request body must be a JSON object."]

    errors: list[str] = []

    # Top-level required fields
    errors += _required(data, "recurly_token", "plan_code", "first_name", "last_name", "email")

    # Email format
    email = data.get("email", "")
    if email and not re.match(r"^[^\s@]+@[^\s@]+\.[^\s@]+$", email):
        errors.append("'email' is not a valid email address.")

    # Plan code whitelist
    plan_code = data.get("plan_code", "")
    if plan_code and plan_code not in VALID_PLAN_CODES:
        errors.append(f"'plan_code' '{plan_code}' is not a recognised plan.")

    # Address sub-object
    address = data.get("address")
    if not isinstance(address, dict):
        errors.append("'address' must be an object.")
    else:
        errors += _required(address, "address1", "city", "state", "zip")

        state = address.get("state", "")
        if state and state.upper() not in US_STATES:
            errors.append(f"'address.state' '{state}' is not a valid US state abbreviation.")

        zip_code = address.get("zip", "")
        if zip_code and not re.match(r"^\d{5}$", str(zip_code)):
            errors.append("'address.zip' must be a 5-digit US ZIP code.")

    return errors
