"""Upload na YouTube z zaplanowaną publikacją (status.publishAt).

Autoryzacja: OAuth refresh token kanału (jednorazowo: python src/youtube_auth.py).
Zmienne: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN.

Uwaga: projekty Google Cloud bez audytu YouTube API (utworzone po 28.07.2020) —
filmy wgrane przez videos.insert zostają zablokowane jako prywatne, publishAt nie zadziała.
"""
from __future__ import annotations

import os
import time
from datetime import datetime, timezone
from pathlib import Path

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_URI = "https://oauth2.googleapis.com/token"
CATEGORY_ID = os.environ.get("YT_CATEGORY_ID", "27")  # 27 = Education
SYNTHETIC = os.environ.get("YT_SYNTHETIC_MEDIA", "false").lower() == "true"
LANG = (os.environ.get("CHANNEL", "pl").strip().lower() or "pl")  # pl / de / en / hi


def _service():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    if not os.environ.get("YT_REFRESH_TOKEN"):  # sekret kanału: YT_REFRESH_TOKEN_PL / _DE / … / _UA
        from lang import L
        os.environ["YT_REFRESH_TOKEN"] = os.environ.get(f"YT_REFRESH_TOKEN_{L.yt}", "")

    missing = [k for k in ("YT_CLIENT_ID", "YT_CLIENT_SECRET", "YT_REFRESH_TOKEN") if not os.environ.get(k)]
    if missing:
        raise RuntimeError(f"Brak zmiennych: {', '.join(missing)}")
    creds = Credentials(
        None,
        refresh_token=os.environ["YT_REFRESH_TOKEN"],
        token_uri=TOKEN_URI,
        client_id=os.environ["YT_CLIENT_ID"],
        client_secret=os.environ["YT_CLIENT_SECRET"],
        scopes=SCOPES,
    )
    return build("youtube", "v3", credentials=creds, cache_discovery=False)


def video_body(title: str, description: str, tags: list, publish_at: datetime, now: bool = False) -> dict:
    """now=True: od razu publiczny (odcinek "na dziś"); inaczej private + publishAt."""
    if publish_at.tzinfo is None:
        raise ValueError("publish_at musi mieć strefę czasową")
    status = ({"privacyStatus": "public"} if now else {
        "privacyStatus": "private",  # publishAt wymaga private
        "publishAt": publish_at.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.000Z"),
    })
    return {
        "snippet": {
            "title": title[:100],
            "description": description[:5000],
            "tags": tags,
            "categoryId": CATEGORY_ID,
            "defaultLanguage": LANG,
            "defaultAudioLanguage": LANG,
        },
        "status": {
            **status,
            "selfDeclaredMadeForKids": False,
            "containsSyntheticMedia": SYNTHETIC,
        },
    }


def upload(video_path: Path, body: dict, service=None, retries: int = 5) -> str:
    """Zwraca videoId. Upload wznawialny, ponawianie przy 5xx/sieci."""
    from googleapiclient.errors import HttpError
    from googleapiclient.http import MediaFileUpload

    yt = service or _service()
    media = MediaFileUpload(str(video_path), mimetype="video/mp4", chunksize=8 * 1024 * 1024, resumable=True)
    req = yt.videos().insert(part="snippet,status", body=body, media_body=media)
    response, attempt = None, 0
    while response is None:
        try:
            _, response = req.next_chunk()
        except HttpError as e:
            if e.resp.status not in (500, 502, 503, 504) or attempt >= retries:
                raise
            attempt += 1
            time.sleep(2 ** attempt)
        except (ConnectionError, TimeoutError):
            if attempt >= retries:
                raise
            attempt += 1
            time.sleep(2 ** attempt)
    if "id" not in response:
        raise RuntimeError(f"Nieoczekiwana odpowiedź YouTube: {response}")
    return response["id"]


def set_thumbnail(video_id: str, image: Path, service=None) -> None:
    """Okładka (OpenAI albo nasza). Wymaga zweryfikowanego kanału (własne miniatury); błąd nie blokuje odcinka."""
    from googleapiclient.http import MediaFileUpload

    yt = service or _service()
    yt.thumbnails().set(videoId=video_id, media_body=MediaFileUpload(str(image), mimetype="image/jpeg")).execute()
