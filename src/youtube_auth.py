"""Jednorazowe uzyskanie refresh tokena YouTube (uruchom lokalnie, z przeglądarką).

  pip install google-auth-oauthlib
  python src/youtube_auth.py client_secret.json

client_secret.json: Google Cloud Console -> APIs & Services -> Credentials ->
OAuth client ID typu "Desktop app" (włączone YouTube Data API v3).
Wynik wklej do sekretów repo: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN.
Zaloguj się kontem, które zarządza kanałem.
"""
import json
import sys

from google_auth_oauthlib.flow import InstalledAppFlow

from youtube_upload import SCOPES


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    flow = InstalledAppFlow.from_client_secrets_file(sys.argv[1], SCOPES)
    creds = flow.run_local_server(port=0, access_type="offline", prompt="consent")
    with open(sys.argv[1], encoding="utf-8") as fh:
        info = next(iter(json.load(fh).values()))
    print("YT_CLIENT_ID=" + info["client_id"])
    print("YT_CLIENT_SECRET=" + info["client_secret"])
    print("YT_REFRESH_TOKEN=" + creds.refresh_token)
    return 0


if __name__ == "__main__":
    sys.exit(main())
