import json
import subprocess
import threading
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from functools import partial
from pathlib import Path
from typing import Tuple, Optional

import requests
from tqdm import tqdm


class InstagramAPIError(Exception):
    pass


API_VERSION = "v22.0"
HTTP_PORT = 8000
SERVE_DIR = "output/to_publish"


class MonitoringHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, video_filename=None, download_started=None, download_finished=None, **kwargs):
        self.video_filename = video_filename
        self.download_started = download_started
        self.download_finished = download_finished
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.video_filename and self.video_filename in self.path:
            self.download_started.set()
        super().do_GET()

    def copyfile(self, source, outputfile):
        super().copyfile(source, outputfile)
        if self.video_filename:
            self.download_finished.set()


def _load_config(config_path: str = None) -> dict:
    config_path = config_path or ("config/ig_api.json" if Path("config/ig_api.json").exists() else "ig_api.json")
    cfg = json.loads(Path(config_path).read_text()).get("ig_api", {})
    user_id = cfg.get("user_id")
    if not user_id:
        raise InstagramAPIError("Missing 'user_id' in ig_api.json under ig_api.user_id")
    return cfg


def _load_token(token_path: str = "ig_token.txt") -> str:
    p = Path(token_path)
    if not p.exists():
        raise InstagramAPIError(f"Token file not found: {token_path}. Run instagram_oauth.py first.")
    token = p.read_text().strip()
    if not token:
        raise InstagramAPIError(f"Token file {token_path} is empty.")
    return token


def _get_video_description(filepath: Path) -> str:
    cmd = ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", str(filepath)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise InstagramAPIError(f"ffprobe error: {proc.stderr.strip()}")
    info = json.loads(proc.stdout)
    tags = info.get("format", {}).get("tags", {})
    desc = tags.get("description")
    if not desc:
        raise InstagramAPIError("No 'description' metadata tag found in video")
    return desc


def _start_http_server(directory: str, port: int, video_filename: str, download_started, download_finished) -> HTTPServer:
    handler = partial(
        MonitoringHandler,
        directory=directory,
        video_filename=video_filename,
        download_started=download_started,
        download_finished=download_finished,
    )
    server = HTTPServer(("0.0.0.0", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _start_ngrok(port: int) -> Tuple[subprocess.Popen, str]:
    proc = subprocess.Popen(
        ["ngrok", "http", str(port), "--log", "stdout"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    public_url = None
    assert proc.stdout is not None
    for line in proc.stdout:
        if "url=https://" in line:
            parts = line.strip().split("url=")
            if len(parts) > 1:
                public_url = parts[1].split()[0].strip()
                break
    if not public_url:
        proc.terminate()
        raise InstagramAPIError("Failed to obtain public URL from ngrok")
    return proc, public_url


def publish_reel(filepath: str, caption: Optional[str] = None) -> dict:
    cfg = _load_config()
    access_token = _load_token()
    user_id = cfg["user_id"]

    video_path = Path(filepath)
    if not video_path.is_file():
        raise InstagramAPIError(f"Video file not found: {filepath}")

    if caption is None:
        caption = _get_video_description(video_path)

    download_started = threading.Event()
    download_finished = threading.Event()

    server = _start_http_server(SERVE_DIR, HTTP_PORT, video_path.name, download_started, download_finished)

    try:
        ngrok_proc, public_base = _start_ngrok(HTTP_PORT)
        try:
            video_url = f"{public_base}/{video_path.name}"
            init_resp = requests.post(
                f"https://graph.instagram.com/{user_id}/media",
                params={"access_token": access_token},
                data={
                    "media_type": "REELS",
                    "video_url": video_url,
                    "caption": caption,
                },
            )
            if not init_resp.ok:
                raise InstagramAPIError(f"Init upload failed: {init_resp.text}")
            creation_id = init_resp.json().get("id")
            if not creation_id:
                raise InstagramAPIError(f"No creation ID returned: {init_resp.text}")

            if not download_started.wait(timeout=60 * 10):
                raise InstagramAPIError("Instagram never attempted to download the video.")
            if not download_finished.wait(timeout=60 * 30):
                raise InstagramAPIError("Instagram started download but didn't complete it in time.")

            for _ in tqdm(range(5)):
                time.sleep(30)
                status_resp = requests.get(
                    f"https://graph.instagram.com/{creation_id}",
                    params={"fields": "status_code", "access_token": access_token},
                )
                status_resp.raise_for_status()
                status = status_resp.json().get("status_code")
                if status == "FINISHED":
                    break
                if status == "ERROR":
                    raise InstagramAPIError(f"Video processing error: {status_resp.text}")
            else:
                raise InstagramAPIError(f"Media not ready after polling: {status_resp.text}")

            pub_resp = requests.post(
                f"https://graph.instagram.com/{user_id}/media_publish",
                params={"access_token": access_token},
                data={"creation_id": creation_id},
            )
            if not pub_resp.ok:
                raise InstagramAPIError(f"Publish failed: {pub_resp.text}")

            return pub_resp.json()

        finally:
            ngrok_proc.terminate()
            ngrok_proc.wait(timeout=10)

    finally:
        server.shutdown()
        server.server_close()
*** End Patch insjson ***!
