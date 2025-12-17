"""Command-line entrypoint for the Reels Factory pipeline."""
from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import typer

from .config import load_config
from .ingest import scrape_reddit_posts
from .paths import OutputPaths
from .render import create_reel
from .rewrite import create_llm, generate_hashtags, process_text
from .utils import reel_id_from_title

app = typer.Typer(add_completion=False, help="Automate short-form narrated reels.")


def setup_logging(log_dir: Path) -> None:
    log_dir.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(message)s",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(log_dir / "pipeline.log", encoding="utf-8"),
        ],
    )


@app.command()
def scrape(
    config_path: str = typer.Option("config/config.json", help="Path to config JSON."),
    output: Optional[str] = typer.Option(None, help="Override parquet output path."),
):
    """Scrape Reddit stories into a parquet cache."""
    cfg = load_config(config_path)
    paths = OutputPaths.from_config(cfg)
    paths.ensure_all()
    setup_logging(paths.logs_dir)
    out = output or paths.raw_posts_path
    logging.info("Scraping Reddit stories to %s", out)
    scrape_reddit_posts(config_path=config_path, output_path=out)
    logging.info("Done.")


@app.command()
def rewrite(
    config_path: str = typer.Option("config/config.json", help="Path to config JSON."),
    input_path: Optional[str] = typer.Option(None, help="Parquet file with scraped posts."),
    output_path: Optional[str] = typer.Option(None, help="Where to save rewritten posts parquet."),
    limit: int = typer.Option(10, help="Number of posts to process."),
):
    """Rewrite posts into 60s narration + hashtags."""
    cfg = load_config(config_path)
    paths = OutputPaths.from_config(cfg)
    paths.ensure_all()
    setup_logging(paths.logs_dir)

    src_path = Path(input_path) if input_path else paths.raw_posts_path
    dest_path = Path(output_path) if output_path else paths.rewritten_posts_path

    if not src_path.exists():
        raise FileNotFoundError(f"{src_path} not found. Run `scrape` first.")

    df = pd.read_parquet(src_path)
    logging.info("Loaded %s posts", len(df))

    rows = []
    llm = create_llm()
    try:
        for idx, (_, post) in enumerate(df.head(limit).iterrows(), start=1):
            story = post.get("contents") or post.get("text") or post.get("title", "")
            rewritten = process_text(story, llm=llm)
            if not rewritten:
                logging.warning("Skipping empty rewrite for %s", post.get("title"))
                continue
            reel_id = reel_id_from_title(post.get("title", f"post-{idx}"))
            hashtags = generate_hashtags(rewritten, post.get("subreddit", "stories"), llm=llm)
            rows.append(
                {
                    "reel_id": reel_id,
                    "title": post.get("title"),
                    "subreddit": post.get("subreddit"),
                    "url": post.get("url"),
                    "rewritten": rewritten,
                    "hashtags": hashtags,
                }
            )
            logging.info("Rewrote %s -> reel_id=%s", post.get("title"), reel_id)
    finally:
        llm.close()

    result = pd.DataFrame(rows)
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(dest_path)
    logging.info("Saved %s rewritten posts to %s", len(result), dest_path)


@app.command("generate")
def generate_reels(
    config_path: str = typer.Option("config/config.json", help="Path to config JSON."),
    input_path: Optional[str] = typer.Option(None, help="Parquet with rewritten posts."),
    limit: int = typer.Option(3, help="How many reels to render."),
):
    """Generate narrated reels (audio + captions + vertical video)."""
    cfg = load_config(config_path)
    paths = OutputPaths.from_config(cfg)
    paths.ensure_all()
    setup_logging(paths.logs_dir)

    src_path = Path(input_path) if input_path else paths.rewritten_posts_path
    if not src_path.exists():
        raise FileNotFoundError(f"{src_path} not found. Run `rewrite` first.")

    df = pd.read_parquet(src_path)
    generated = []
    for _, row in df.head(limit).iterrows():
        post_text = row["rewritten"]
        post_title = row["title"]
        post_description = row.get("hashtags", "")
        logging.info("Rendering reel for %s", post_title)
        output_path = create_reel(
            post_text=post_text,
            post_title=post_title,
            config=cfg,
            post_description=post_description,
        )
        generated.append(str(output_path))
        logging.info("Reel ready at %s", output_path)

    if generated:
        logging.info("Generated %d reel(s).", len(generated))
    else:
        logging.warning("No reels generated.")


@app.command()
def publish(
    folder: str = typer.Option("output/to_publish", help="Folder with MP4s to upload."),
):
    """
    Publish rendered reels to Instagram via the Graph API.
    Expects valid OAuth token and app credentials in ig_api.json / env.
    """
    from instagram_api import publish_reel
    from glob import glob

    files = glob(f"{folder.rstrip('/')}{'/' if not folder.endswith('/') else ''}*.mp4")
    if not files:
        typer.echo(f"No mp4 files found in {folder}")
        raise typer.Exit(code=0)

    for file in files:
        typer.echo(f"Publishing {file}...")
        publish_reel(file)
        typer.echo(f"Published {file}")


def main():
    app()


if __name__ == "__main__":
    main()
