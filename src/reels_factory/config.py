"""Configuration loader with environment overrides."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Dict

from dotenv import load_dotenv

DEFAULT_PATHS = [
    Path("config/config.json"),
    Path("config.json"),
    Path("config/config.example.json"),
]


def _find_config_path(explicit: str | None) -> Path:
    """Return the first existing config path."""
    if explicit:
        return Path(explicit)
    for candidate in DEFAULT_PATHS:
        if candidate.exists():
            return candidate
    raise FileNotFoundError("No config file found. Create config/config.json from config/config.example.json")


def load_config(config_path: str | None = None) -> Dict[str, Any]:
    """
    Load configuration from disk and apply environment overrides for secrets.
    """
    load_dotenv()
    cfg_path = _find_config_path(config_path)
    with cfg_path.open("r", encoding="utf-8") as f:
        cfg = json.load(f)

    reddit = cfg.get("reddit_scraper", {}).get("reddit_api", {})
    reddit["client_id"] = os.environ.get("REDDIT_CLIENT_ID", reddit.get("client_id"))
    reddit["client_secret"] = os.environ.get("REDDIT_CLIENT_SECRET", reddit.get("client_secret"))
    reddit["user_agent"] = os.environ.get("REDDIT_USER_AGENT", reddit.get("user_agent", "ai_content_scraper"))
    cfg.setdefault("reddit_scraper", {})["reddit_api"] = reddit

    ig = cfg.setdefault("instagram", {})
    ig["app_id"] = os.environ.get("INSTAGRAM_APP_ID", ig.get("app_id"))
    ig["app_secret"] = os.environ.get("INSTAGRAM_APP_SECRET", ig.get("app_secret"))
    ig["user_id"] = os.environ.get("INSTAGRAM_USER_ID", ig.get("user_id"))
    ig["token"] = os.environ.get("INSTAGRAM_TOKEN", ig.get("token"))

    assets = cfg.setdefault("assets", {})
    assets.setdefault("output_root", "output")
    assets.setdefault("background_glob", "videos/*.mp4")
    cfg["assets"] = assets

    return cfg
