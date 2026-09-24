"""Autopublikacja: co INTERVAL_DAYS dni o PUBLISH_HOUR (strefa PUBLISH_TZ).

Uruchamiany codziennie (GitHub Actions). Utrzymuje BUFFER zaplanowanych odcinków
w przyszłości: bierze następną gotową partię z catalog/games.json, w razie potrzeby
generuje scenariusz (script_gen.py), renderuje (main.py) i wgrywa na YouTube jako
prywatny z publishAt — YouTube sam publikuje o zadanej godzinie. Do tego czasu film
można obejrzeć i poprawić/usunąć w YouTube Studio.

Partia jest gotowa, gdy: games/<id>.pgn istnieje, pgn_verified == true, disputed != true.

  python src/scheduler.py --plan        # co i kiedy zostanie opublikowane, bez zmian
  python src/scheduler.py               # jeden krok (max MAX_PER_RUN odcinków)
  python src/scheduler.py --no-upload   # wszystko poza uploadem (test)
  python src/scheduler.py --dry-tts     # jak --no-upload, ale bez Inworld (cisza)
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
CATALOG = ROOT / "catalog" / "games.json"
STATE = ROOT / "state" / "schedule.json"

TZ = ZoneInfo(os.environ.get("PUBLISH_TZ", "Europe/Kyiv"))
PUBLISH_HOUR = int(os.environ.get("PUBLISH_HOUR", "10"))
INTERVAL_DAYS = int(os.environ.get("INTERVAL_DAYS", "3"))
BUFFER = int(os.environ.get("BUFFER", "2"))            # ile odcinków trzymać zaplanowanych naprzód
MAX_PER_RUN = int(os.environ.get("MAX_PER_RUN", "1"))
MIN_LEAD = timedelta(hours=int(os.environ.get("MIN_LEAD_HOURS", "6")))  # zapas na przetworzenie przez YouTube
LOW_QUEUE_WARN = 3


def load_json(path: Path, default):
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slot_at(day: date) -> datetime:
    """10:00 czasu lokalnego danego dnia (z uwzględnieniem zmiany czasu) w UTC."""
    return datetime.combine(day, time(PUBLISH_HOUR), tzinfo=TZ).astimezone(timezone.utc)


def next_slot(episodes: list, now: datetime, first_day: date | None) -> datetime:
    earliest = now + MIN_LEAD
    if episodes:
        last = max(datetime.fromisoformat(e["publish_at"]) for e in episodes)
        day = last.astimezone(TZ).date() + timedelta(days=INTERVAL_DAYS)
    else:
        day = first_day or earliest.astimezone(TZ).date()
    while slot_at(day) < earliest:  # przegapione terminy przesuwamy o pełne interwały
        day += timedelta(days=INTERVAL_DAYS)
    return slot_at(day)


def ready(game: dict) -> bool:
    return (bool(game.get("pgn_verified")) and not game.get("disputed")
            and (ROOT / "games" / f"{game['id']}.pgn").exists())


def queue(catalog: dict, episodes: list) -> list:
    done = {e["id"] for e in episodes}
    return [g for g in sorted(catalog["games"], key=lambda g: g["n"]) if g["id"] not in done and ready(g)]


def run(cmd: list) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)


def describe(game: dict, script: dict) -> tuple[str, str, list]:
    white, black = game.get("white_pl") or game["white"], game.get("black_pl") or game["black"]
    who = f"{white} – {black}"
    place = ", ".join(str(x) for x in (game.get("site_pl") or game.get("site"), game.get("year")) if x)
    title = f"{script.get('title', who)} | {who} ({game['year']})"
    lines = [who, place, (game.get("label_pl") or game.get("event") or "").replace(" · ", ", "), ""]
    if game.get("result"):
        lines.append(f"Wynik: {game['result']}")
    from players import side
    credits = []
    for color in ("white", "black"):
        c = side(game, color, game[color])["credit"]
        if c:
            credits.append(f"{side(game, color, game[color])['name']}: {c.get('author') or 'autor nieznany'}, "
                           f"{c.get('license')}, {c.get('source_url')}")
    if credits:
        lines += ["", "Zdjęcia (Wikimedia Commons):", *credits]
    lines += ["", "#szachy #chess #historiaszachów"]
    tags = ["szachy", "chess", "partia szachowa", "historia szachów",
            white.split()[-1], black.split()[-1]]
    return title, "\n".join(lines).strip(), tags


def produce(game: dict, publish_at: datetime, no_upload: bool, dry_tts: bool = False) -> dict:
    gid = game["id"]
    pgn = ROOT / "games" / f"{gid}.pgn"
    script_path = ROOT / "scripts" / f"{gid}.json"
    video = ROOT / "out" / f"{gid}.mp4"
    py = sys.executable

    if not script_path.exists():
        run([py, str(SRC / "script_gen.py"), "--pgn", str(pgn), "--out", str(script_path), "--name", gid])
    run([py, str(SRC / "main.py"), "--pgn", str(pgn), "--script", str(script_path), "--out", str(video)]
        + (["--dry-run"] if dry_tts else []))

    script = load_json(script_path, {})
    title, description, tags = describe(game, script)
    episode = {"id": gid, "publish_at": publish_at.isoformat(), "title": title, "video_id": None}
    if no_upload:
        print(f"[no-upload] {title} -> {publish_at.astimezone(TZ):%Y-%m-%d %H:%M %Z}")
        return episode

    from youtube_upload import upload, video_body
    episode["video_id"] = upload(video, video_body(title, description, tags, publish_at))
    print(f"Wgrano {episode['video_id']}: {title} -> {publish_at.astimezone(TZ):%Y-%m-%d %H:%M %Z}")
    return episode


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--no-upload", action="store_true")
    ap.add_argument("--dry-tts", action="store_true", help="test: cisza zamiast Inworld (wymusza --no-upload)")
    ap.add_argument("--first-day", help="YYYY-MM-DD pierwszej publikacji (tylko gdy brak historii)")
    args = ap.parse_args()
    if args.dry_tts:
        args.no_upload = True

    catalog = load_json(CATALOG, {"games": []})
    state = load_json(STATE, {"episodes": []})
    episodes = state["episodes"]
    now = datetime.now(timezone.utc)
    first_day = date.fromisoformat(args.first_day or state.get("first_day") or "") \
        if (args.first_day or state.get("first_day")) else None

    q = queue(catalog, episodes)
    if len(q) < LOW_QUEUE_WARN:
        print(f"::warning::W kolejce tylko {len(q)} gotowych partii (PGN zweryfikowane)")

    if args.plan:
        eps = list(episodes)
        for g in q[:10]:
            slot = next_slot(eps, now, first_day)
            print(f"{slot.astimezone(TZ):%Y-%m-%d %H:%M %Z}  #{g['n']:>3}  {g['id']}")
            eps.append({"id": g["id"], "publish_at": slot.isoformat()})
        return 0

    made = 0
    while made < MAX_PER_RUN:
        future = [e for e in episodes if datetime.fromisoformat(e["publish_at"]) > now]
        if len(future) >= BUFFER:
            print(f"Zaplanowane naprzód: {len(future)} (bufor {BUFFER}) — nic do zrobienia")
            break
        if not q:
            print("::error::Brak gotowych partii — dodaj zweryfikowane PGN (src/pgn_collect.py)")
            return 1
        game = q.pop(0)
        slot = next_slot(episodes, now, first_day)
        episode = produce(game, slot, args.no_upload, args.dry_tts)
        if args.no_upload:
            break
        episodes.append(episode)
        if args.first_day and not state.get("first_day"):
            state["first_day"] = args.first_day
        save_json(STATE, state)  # zapis po każdym uploadzie — nie wgrywać drugi raz
        made += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
