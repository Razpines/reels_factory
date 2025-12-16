#!/usr/bin/env python3
"""
flask_oauth.py

Module to obtain a valid long-lived Instagram Business Login token.
Exports:
    get_long_lived_token() -> str
"""

import json
import os
import socket
import threading
import time
import webbrowser
from pathlib import Path

import requests
from flask import Flask, request

CONFIG_PATH = Path("config/ig_api.json") if Path("config/ig_api.json").exists() else Path("ig_api.json")
TOKEN_PATH = Path("ig_token.txt")
CERT_PATH = Path("cert.pem")
KEY_PATH = Path("key.pem")
HOST = "0.0.0.0"
PORT = 5000
REDIRECT_URI = f"https://localhost:{PORT}/auth/callback"

_cfg = json.loads(CONFIG_PATH.read_text())["ig_api"]
CLIENT_ID = os.environ.get("INSTAGRAM_APP_ID", _cfg["app_id"])
CLIENT_SECRET = os.environ.get("INSTAGRAM_APP_SECRET", _cfg["app_secret"])

LOGIN_URL = (
    "https://www.instagram.com/oauth/authorize"
    "?enable_fb_login=0&force_authentication=1"
    f"&client_id={CLIENT_ID}"
    f"&redirect_uri={REDIRECT_URI}"
    "&response_type=code"
    "&scope=instagram_business_basic,instagram_business_content_publish"
)


class InstagramAuthError(Exception):
    pass


def _refresh_token(old_token: str) -> str:
    resp = requests.get(
        "https://graph.instagram.com/refresh_access_token",
        params={
            "grant_type": "ig_refresh_token",
            "access_token": old_token,
        },
    )
    data = resp.json()
    if not resp.ok or "access_token" not in data:
        raise InstagramAuthError(f"Refresh failed: {data}")
    return data["access_token"]


def _run_oauth_flow() -> str:
    app = Flask(__name__)

    @app.route("/auth/callback")
    def _callback():
        code = request.args.get("code")
        if not code:
            return "Missing code", 400

        r1 = requests.post(
            "https://api.instagram.com/oauth/access_token",
            data={
                "client_id": CLIENT_ID,
                "client_secret": CLIENT_SECRET,
                "grant_type": "authorization_code",
                "redirect_uri": REDIRECT_URI,
                "code": code,
            },
        )
        r1.raise_for_status()
        short_token = r1.json().get("access_token")
        if not short_token:
            return f"No short token: {r1.text}", 400

        r2 = requests.get(
            "https://graph.instagram.com/access_token",
            params={
                "grant_type": "ig_exchange_token",
                "client_secret": CLIENT_SECRET,
                "access_token": short_token,
            },
        )
        r2.raise_for_status()
        long_token = r2.json().get("access_token")
        if not long_token:
            return f"No long token: {r2.text}", 400

        TOKEN_PATH.write_text(long_token)
        shutdown_fn = request.environ.get("werkzeug.server.shutdown")
        if shutdown_fn:
            shutdown_fn()
        return ("Success! Long-lived token saved to ig_token.txt. You can close this tab.", 200)

    def _serve():
        app.run(host=HOST, port=PORT, ssl_context=(str(CERT_PATH), str(KEY_PATH)))

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()

    for _ in range(50):
        try:
            sock = socket.create_connection(("127.0.0.1", PORT), timeout=1)
            sock.close()
            break
        except OSError:
            time.sleep(0.1)
    else:
        raise InstagramAuthError("Flask server did not start in time")

    webbrowser.open(LOGIN_URL, new=1)
    thread.join()

    if not TOKEN_PATH.exists():
        raise InstagramAuthError("OAuth flow failed: no token saved")
    return TOKEN_PATH.read_text().strip()


def get_long_lived_token() -> str:
    if TOKEN_PATH.exists():
        old = TOKEN_PATH.read_text().strip()
        try:
            new = _refresh_token(old)
            TOKEN_PATH.write_text(new)
            return new
        except Exception:
            pass
    return _run_oauth_flow()
