"""Reddit ingest and filtering."""
from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Optional

import pandas as pd
import praw
import torch
from detoxify import Detoxify
from llama_cpp import Llama
from tqdm import tqdm

from .config import load_config
from .paths import OutputPaths
from .utils import apply_patterns


def _clean_post_body(text: str) -> str:
    """
    Trim common edit/update sections that distract from narration.
    """
    parts = [
        "Edit: ",
        "EDIT",
        "update",
        "Update",
        "UPDATE",
        "edit",
        "update,",
        "update:",
    ]
    for token in parts:
        if token in text:
            text = text.split(token)[0]
    return text


def detect_gender_with_llm(text: str, llm: Llama) -> str:
    """
    Optional narrator gender detection using a constrained grammar.
    """
    prompt = f"""
Based on the following story, determine the gender of the narrator.
Answer in a single word only ("male" or "female"). Assume heterosexual pairing if ambiguous.

[START OF STORY]
{text}
[END OF STORY]

Narrator's gender:"""
    resp = llm(
        prompt,
        temperature=0.0,
        max_tokens=1,
        grammar=None,
    )
    return resp["choices"][0]["text"].strip().lower() or "male"


def scrape_reddit_posts(
    llm: Optional[Llama] = None,
    config_path: str | None = None,
    config: Optional[dict] = None,
    output_path: str | Path | None = None,
    device: Optional[str] = None,
    enable_gender: bool = False,
) -> pd.DataFrame:
    """
    Scrape Reddit posts and save them to a parquet file.

    Args:
        llm: Optional Llama instance for gender detection.
        config_path: Path to config JSON (used if config is None).
        config: Preloaded config dict (overrides config_path).
        output_path: Destination parquet path; defaults to assets.output_root/top_reddit_stories.parquet.
        device: Torch device for Detoxify. Defaults to CUDA if available.
        enable_gender: If True, run gender detection with provided llm (or a new one).
    """
    cfg = config or load_config(config_path)
    paths = OutputPaths.from_config(cfg)
    paths.ensure_all()

    reddit_config = cfg["reddit_scraper"]
    client_id = reddit_config["reddit_api"]["client_id"]
    client_secret = reddit_config["reddit_api"]["client_secret"]
    user_agent = reddit_config["reddit_api"]["user_agent"]
    subreddits = reddit_config["subreddits"]
    post_filter = reddit_config.get("post_filter", "hot")
    time_filter = reddit_config.get("time_filter", "month")
    post_limit = reddit_config.get("post_limit", 50)
    post_length_limits = reddit_config.get("post_length", {"lower": 20, "upper": 300})
    sort_by = reddit_config.get("sort_by", "num_comments")
    normalization_patterns = reddit_config["story_normalization"]

    detox_device = device or ("cuda" if torch.cuda.is_available() else "cpu")
    detoxify_classifier = Detoxify("original", device=detox_device)

    reddit = praw.Reddit(
        client_id=client_id,
        client_secret=client_secret,
        user_agent=user_agent,
    )

    private_llm = enable_gender and llm is None
    if private_llm:
        llm = Llama(
            model_path="models/llama-3.1-8b-instruct-q6_k.gguf",
            n_gpu_layers=-1,
            n_ctx=2048,
            verbose=False,
            streaming=False,
            device="cuda" if torch.cuda.is_available() else "cpu",
        )

    posts: list[dict] = []

    for sub in subreddits:
        subreddit = reddit.subreddit(sub)
        if post_filter == "hot":
            posts_iterator = subreddit.hot(limit=post_limit)
        elif post_filter == "new":
            posts_iterator = subreddit.new(limit=post_limit)
        elif post_filter == "controversial":
            posts_iterator = subreddit.controversial(time_filter=time_filter, limit=post_limit)
        elif post_filter == "top":
            posts_iterator = subreddit.top(time_filter=time_filter, limit=post_limit)
        else:
            logging.warning("Invalid post_filter %s, defaulting to hot", post_filter)
            posts_iterator = subreddit.hot(limit=post_limit)

        for post in tqdm(posts_iterator, desc=f"Fetching from r/{sub}"):
            post_contents = _clean_post_body("\n".join([post.title, post.selftext]))
            post_contents = apply_patterns(post_contents, normalization_patterns)

            post_length = len(post_contents.split(" "))
            if post_length < post_length_limits["lower"] or post_length > post_length_limits["upper"]:
                continue

            toxicity_scores = detoxify_classifier.predict(post_contents)
            narrator_gender = None
            if enable_gender and llm is not None:
                narrator_gender = detect_gender_with_llm(post_contents, llm)

            posts.append(
                {
                    "subreddit": sub,
                    "title": post.title,
                    "url": f"https://www.reddit.com{post.permalink}",
                    "text": post.selftext,
                    "contents": post_contents,
                    "score": post.score,
                    "num_comments": post.num_comments,
                    "created_utc": post.created_utc,
                    "length": len(post.selftext.split(" ")),
                    "narrator_gender": narrator_gender,
                    **toxicity_scores,
                }
            )

    df = pd.DataFrame(posts).sort_values(sort_by, ascending=False)
    destination = Path(output_path) if output_path else paths.raw_posts_path
    destination.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(destination)

    if private_llm and llm is not None:
        llm.close()

    logging.info("Scraping completed and saved to %s (%d posts)", destination, len(df))
    return df
