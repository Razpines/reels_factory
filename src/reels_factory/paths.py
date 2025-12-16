"""Path helpers for deterministic artifact layout."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass
class OutputPaths:
    """Normalized output paths derived from config assets."""

    root: Path

    @classmethod
    def from_config(cls, cfg: dict) -> "OutputPaths":
        root = Path(cfg.get("assets", {}).get("output_root", "output"))
        return cls(root=root)

    @property
    def narration_dir(self) -> Path:
        return self.root / "narration"

    @property
    def reels_dir(self) -> Path:
        return self.root / "reels"

    @property
    def subtitles_dir(self) -> Path:
        return self.narration_dir

    @property
    def logs_dir(self) -> Path:
        return self.root / "logs"

    @property
    def raw_posts_path(self) -> Path:
        return self.root / "top_reddit_stories.parquet"

    @property
    def rewritten_posts_path(self) -> Path:
        return self.root / "rewritten_posts.parquet"

    def ensure_all(self) -> None:
        for path in [
            self.root,
            self.narration_dir,
            self.reels_dir,
            self.subtitles_dir,
            self.logs_dir,
            self.raw_posts_path.parent,
            self.rewritten_posts_path.parent,
        ]:
            path.mkdir(parents=True, exist_ok=True)
