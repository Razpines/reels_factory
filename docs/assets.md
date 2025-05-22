# Background video assets

The pipeline expects background clips locally in `videos/` (default glob `videos/*.mp4`). These files are large and typically copyrighted, so **do not commit them to the repo**. Instead, keep them locally or host them in a private bucket/drive.

## What works well
- Satisfying/loopable gameplay: Minecraft parkour, CS surf/bhop, Rocket League drifts.
- Hypnotic/mesmerizing: kinetic sand, oddly satisfying, marble runs, slime cuts.
- High motion but simple focus: low HUD clutter, minimal overlays, no watermarks.
- Long enough to crop to 9:16 and still fit 60–75s narration.

## How to source
- Use `yt-dlp` with a permissive search query, then manually curate:
  ```
  yt-dlp -f "bv*[ext=mp4]+ba[ext=m4a]/mp4" -o "videos/%(title).90s.%(ext)s" "<video-url>"
  ```
- Aim for 1080p+; higher bitrate helps after cropping and recompression.
- Avoid creator watermarks and visible usernames.

## Practical tips
- Keep clips in landscape; the render step crops center to 9:16.
- Avoid big FPS counters/minimaps on edges—subtitles sit near the bottom center.
- Trim locally if needed; the renderer already picks a random segment sized to narration length.
- Maintain a small curated set (5–20 clips) to control aesthetic consistency.

## What not to add to git
- `videos/` and any raw downloads.
- Large outputs (`output/reels/*.mp4`, `output/narration/*.wav`). Share samples via a release, drive link, or the demo Instagram account instead of committing binaries.
