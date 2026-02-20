"""
Flowers Forever — Flask Backend
================================
Main application entry point. Registers all API blueprints and
configures Flask + CORS so the frontend can reach the API.

Run locally:
    pip install -r requirements.txt
    cp .env.example .env   # then fill in your Recurly keys
    python app.py

Production (Gunicorn):
    gunicorn -w 4 -b 0.0.0.0:5000 app:app
"""

import os
from flask import Flask, jsonify
from flask_cors import CORS
from dotenv import load_dotenv

# Load .env before anything else
load_dotenv()

from api.subscribe import subscribe_bp
from api.account   import account_bp
from api.webhooks  import webhooks_bp


def create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

    # Allow the static frontend to reach the API.
    # In production, restrict origins to your real domain.
    frontend_url = os.environ.get("FRONTEND_URL", "http://localhost:5500")
    CORS(app, origins=[frontend_url, "http://127.0.0.1:5500"])

    # Register blueprints
    app.register_blueprint(subscribe_bp, url_prefix="/api")
    app.register_blueprint(account_bp,   url_prefix="/api")
    app.register_blueprint(webhooks_bp,  url_prefix="/api")

    # ---- Health check ----
    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "Flowers Forever API"})

    # ---- Generic error handlers ----
    @app.errorhandler(404)
    def not_found(e):
        return jsonify({"success": False, "message": "Endpoint not found"}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        return jsonify({"success": False, "message": "Method not allowed"}), 405

    @app.errorhandler(500)
    def internal_error(e):
        return jsonify({"success": False, "message": "Internal server error"}), 500

    return app


app = create_app()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_ENV") == "development"
    app.run(host="0.0.0.0", port=5001, debug=debug)
