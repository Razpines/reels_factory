# Architecture Overview

This repo is organized as a pipeline that can be run end-to-end or step-by-step through `reels_factory/cli.py`.

```
ingest (reels_factory.ingest) -> rewrite (reels_factory.rewrite) -> tts + captions -> render (reels_factory.render) -> publish (optional)
```

## Stages

- **Ingest**  
  `reels_factory.ingest` pulls top/new posts from configured subreddits, normalizes, and scores toxicity. Output: `output/top_reddit_stories.parquet`.

- **Rewrite**  
  `reels_factory.rewrite` rewrites a post into ~60s narration and generates hashtags. Output: `output/rewritten_posts.parquet`.

- **Voice + Captions + Render**  
  `reels_factory.render` uses Kokoro TTS for narration, Whisper for subtitles, converts VTT→ASS, crops gameplay to 9:16, overlays subs, and mixes audio. Output: `output/reels/*.mp4`.

- **Publish (optional)**  
  `reels_factory.instagram_api` / `reels_factory.flask_oauth` support IG Graph API uploads if you have the right account/app setup.

## Data & Artifacts

- Raw posts: `output/top_reddit_stories.parquet`
- Rewrites: `output/rewritten_posts.parquet`
- Audio/Subtitles: `output/narration/*.wav|*.vtt|*.ass`
- Final reels: `output/reels/*.mp4`
- Logs: `output/logs/pipeline.log`

## Extending

- Swap background sources by changing `assets.background_glob` in config.
- Change caption look in `video_generation.convert_vtt_to_ass`.
- Swap TTS voices in `video_generation.generate_tts`.
- Add moderation gates by plugging additional filters in `reddit_scraper.scrape_reddit_posts`.
