"""
Shared Recurly client — imported by all API modules.
Raises a clear error at startup if the API key is missing.
"""

import os
import recurly


def get_client() -> recurly.Client:
    api_key = os.environ.get("RECURLY_PRIVATE_API_KEY", "")
    if not api_key or api_key == "your-private-api-key-here":
        raise RuntimeError(
            "RECURLY_PRIVATE_API_KEY is not set. "
            "Copy .env.example to .env and add your Recurly private API key."
        )
    return recurly.Client(api_key)


# Module-level singleton — created once when the module is first imported.
try:
    client: recurly.Client = get_client()
except RuntimeError as _e:
    # Allow the app to start without a key so the dev notice still shows.
    # Endpoints will fail gracefully if the key is missing.
    client = None  # type: ignore
    import warnings
    warnings.warn(str(_e))
