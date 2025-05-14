# Publishing via Instagram Graph API (Notes)

The repo includes a basic publisher (`instagram_api.py`, `flask_oauth.py`, `publish.py`) but Instagram imposes strict requirements:

- **Account setup**: You need a Business/Creator IG account linked to a Facebook Page. Personal accounts cannot publish via API.
- **App + roles**: Your Meta app must request `instagram_business_content_publish` permissions. Testers/Developers need to be added to the app.
- **Tokens**: Long-lived user tokens expire (~60 days). `flask_oauth.py` handles refresh/renew but requires a browser login.
- **Hosting the asset**: The Graph API fetches the video from a URL. The sample flow spins up a local HTTP server and exposes it via `ngrok` while Meta downloads it.
- **Friction to expect**: Role/permission errors, Page linkage confusion, and API polling timeouts. Handle errors and be ready to retry manually.

Workflow reminder:

1. Run `python publish.py` (or `make publish`) with `ig_api.json` filled or env vars set.
2. A browser window opens for OAuth if the token is stale.
3. The script serves files from `output/to_publish/` and publishes each `.mp4` it finds.

Review content before uploading; you are responsible for compliance with platform policies.
