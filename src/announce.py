"""Telegram: "Свіже відео на польському каналі!" + link — dopiero gdy film naprawdę wyszedł (decyzja właściciela 19.10.2026).

Przegląda stany wszystkich kanałów (lang.CHANNELS -> state/schedule*.json): odcinki z video_id, których publish_at minął.
Publiczność sprawdza YouTube oEmbed (bez klucza: 200 = film publiczny/niepubliczny, 401/403/404 = prywatny albo usunięty).
Zapowiedziane id trafiają do state/announced.json (osobny plik — bez konfliktów z commitami schedulerów).
Gdy film po ANNOUNCE_STUCK_H godzinach od terminu dalej nie jest publiczny — jedno ostrzeżenie (np. YouTube zablokował
publikację, bo projekt API bez audytu). Starsze niż ANNOUNCE_MAX_AGE_H — oznaczane bez wysyłania (bez zalewu po przerwie).

  python src/announce.py [--dry]
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lang import CHANNELS  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DONE = ROOT / "state" / "announced.json"
OEMBED = "https://www.youtube.com/oembed"
STUCK = timedelta(hours=float(os.environ.get("ANNOUNCE_STUCK_H", "3")))
MAX_AGE = timedelta(hours=float(os.environ.get("ANNOUNCE_MAX_AGE_H", "48")))


def load(path: Path, default):
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else default


def is_public(video_id: str) -> bool | None:
    """True = widać bez logowania; False = prywatny/usunięty; None = nie wiadomo (błąd sieci, 5xx)."""
    try:
        r = requests.get(OEMBED, params={"url": f"https://www.youtube.com/watch?v={video_id}", "format": "json"},
                         timeout=30)
    except requests.RequestException:
        return None
    if r.status_code == 200:
        return True
    return False if r.status_code in (401, 403, 404) else None


def send(text: str) -> None:
    from deliver import _tg
    _tg("sendMessage", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"], "text": text})


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="tylko wypisz, bez Telegrama i bez zapisu")
    args = ap.parse_args()
    if not args.dry and not (os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID")):
        print("Brak TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID — pomijam")
        return 0
    done = load(DONE, {"announced": {}, "warned": {}})
    now = datetime.now(timezone.utc)
    changed = False
    for ch in CHANNELS.values():
        for e in load(ch.state, {"episodes": []})["episodes"]:
            vid = e.get("video_id")
            if not vid or vid in done["announced"] or not e.get("publish_at"):
                continue
            at = datetime.fromisoformat(e["publish_at"])
            if at > now:
                continue
            if now - at > MAX_AGE:  # dawno po premierze (np. po przerwie w automatyzacji) — bez wiadomości
                done["announced"][vid] = {"channel": ch.code, "at": now.isoformat(), "skipped": True}
                changed = True
                continue
            pub = is_public(vid)
            link = f"https://youtu.be/{vid}"
            print(f"[{ch.code}] {vid} termin {at:%Y-%m-%d %H:%M}Z publiczny={pub}")
            if pub:
                if not args.dry:
                    send(f"Свіже відео {ch.name_uk}!\n{link}")
                done["announced"][vid] = {"channel": ch.code, "at": now.isoformat()}
                changed = True
            elif pub is False and now - at > STUCK and vid not in done["warned"]:
                if not args.dry:
                    send(f"⚠️ {ch.flag} Відео мало вийти {ch.name_uk} о {at:%d.%m %H:%M} UTC, "
                         f"але досі не публічне: {link}\nПеревірте YouTube Studio.")
                done["warned"][vid] = now.isoformat()
                changed = True
    if changed and not args.dry:
        DONE.parent.mkdir(parents=True, exist_ok=True)
        DONE.write_text(json.dumps(done, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
