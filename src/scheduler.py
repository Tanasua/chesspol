"""Autopublikacja: co INTERVAL_DAYS dni o PUBLISH_HOUR (strefa PUBLISH_TZ).

Uruchamiany codziennie (GitHub Actions). Utrzymuje BUFFER zaplanowanych odcinków
w przyszłości: bierze następną gotową partię z catalog/games.json, w razie potrzeby
generuje scenariusz (script_gen.py), renderuje (main.py) i wgrywa na YouTube jako
prywatny z publishAt (PUBLISH_MODE=youtube) albo — domyślnie (PUBLISH_MODE=manual) — robi paczkę
do ręcznego uploadu: wideo, okładka, tytuł, opis, tagi i planowana data (src/deliver.py:
out/packages/, GitHub Release, opcjonalnie Telegram).

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
MODE = os.environ.get("PUBLISH_MODE", "manual")  # manual: paczka do ręcznego uploadu; youtube: upload z publishAt


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


def _moves_word(n: int) -> str:
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "ruchy"
    return "ruch" if n == 1 else "ruchów"


def _ts(sec: float) -> str:
    sec = int(sec)
    return f"{sec // 3600}:{sec % 3600 // 60:02d}:{sec % 60:02d}" if sec >= 3600 else f"{sec // 60}:{sec % 60:02d}"


def _chapters(timing: dict) -> list:
    """Rozdziały YouTube: pierwszy 0:00, każdy ≥ 10 s, co najmniej 3 — inaczej brak."""
    out = []
    for ch in timing.get("chapters", []):
        if out and ch["t"] - out[-1]["t"] < 10:
            continue
        out.append(ch)
    if out and timing.get("duration") and timing["duration"] - out[-1]["t"] < 10:
        out.pop()
    return out if len(out) >= 3 and out[0]["t"] == 0 else []


def describe(game: dict, script: dict, pgn: Path | None = None, timing: dict | None = None) -> tuple[str, str, list]:
    from players import side
    white, black = game.get("white_pl") or game["white"], game.get("black_pl") or game["black"]
    who = f"{white} – {black}"
    place = game.get("site_pl") or game.get("site") or ""
    label = (game.get("label_pl") or game.get("event") or "").replace(" · ", ", ")
    title = f"{script.get('title', who)} | {who} ({game['year']})"

    lines = []
    if script.get("description"):
        lines += [script["description"].strip(), ""]
    lines += [f"Białe: {white}", f"Czarne: {black}",
              f"Rok: {game['year']}" + (f" · {place}" if place else ""), label]
    moves_text, n_moves = "", 0
    if pgn and pgn.exists():
        import chess.pgn
        with open(pgn, encoding="utf-8") as fh:
            g = chess.pgn.read_game(fh)
        n_moves = (sum(1 for _ in g.mainline_moves()) + 1) // 2
        moves_text = g.accept(chess.pgn.StringExporter(headers=False, variations=False, comments=False)).strip()
    if game.get("result"):
        lines.append(f"Wynik: {game['result']}" + (f" ({n_moves} {_moves_word(n_moves)})" if n_moves else ""))

    chapters = _chapters(timing or {})
    if chapters:
        lines += ["", "Rozdziały:"] + [f"{_ts(c['t'])} {c['title']}" for c in chapters]
    if moves_text:
        lines += ["", "Zapis partii (PGN):", moves_text]

    credits = []
    for color in ("white", "black"):
        p = side(game, color, game[color])
        c = p["credit"]
        if c:
            credits.append(f"{p['name']}: {c.get('author') or 'autor nieznany'}, {c.get('license')}, {c.get('source_url')}")
    if credits:
        lines += ["", "Zdjęcia (Wikimedia Commons):", *credits]
    verified = "Zapis partii sprawdzony w co najmniej dwóch bazach partii. " if game.get("pgn_verified") else ""
    lines += ["", verified + "Oceny pozycji: Stockfish. Lektor: syntezator mowy. "
                  "Scenariusz przygotowany z pomocą AI na podstawie zapisu partii.",
              "", f"#szachy #chess #historiaszachów #{game['white'].split()[-1]} #{game['black'].split()[-1]}"]
    description = "\n".join(lines).strip()
    if len(description) > 4900:  # limit YouTube: 5000 znaków — najpierw skracamy zapis partii
        description = description.replace(moves_text, moves_text[:max(0, len(moves_text) - (len(description) - 4900))] + " …")
    tags = ["szachy", "chess", "partia szachowa", "historia szachów", "słynne partie szachowe",
            white.split()[-1], black.split()[-1], f"szachy {game['year']}"]
    return title, description, tags


def produce(game: dict, publish_at: datetime, no_upload: bool, dry_tts: bool = False, number: int = 1) -> dict:
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
    title, description, tags = describe(game, script, pgn, load_json(video.with_suffix(".timing.json"), {}))
    when = f"{publish_at.astimezone(TZ):%Y-%m-%d %H:%M} ({TZ.key})"
    episode = {"id": gid, "publish_at": publish_at.isoformat(), "title": title, "mode": MODE}
    if MODE == "manual":
        episode.update(deliver_package(game, pgn, video, title, description, tags, when, number,
                                       remote=not dry_tts))
        print(f"Paczka gotowa: {title} -> {when}")
        return episode
    if no_upload:
        print(f"[no-upload] {title} -> {when}")
        return episode

    from youtube_upload import upload, video_body
    episode["video_id"] = upload(video, video_body(title, description, tags, publish_at))
    print(f"Wgrano {episode['video_id']}: {title} -> {when}")
    return episode


def deliver_package(game: dict, pgn: Path, video: Path, title: str, description: str, tags: list,
                    when: str, number: int, remote: bool = True) -> dict:
    from cover import make_cover
    from deliver import github_release, telegram, write_package
    from pgn_loader import load_game
    from players import side

    g = load_game(pgn)
    tag = f"ep{number:03d}-{game['id']}"
    cover = make_cover(g, title.split(" | ")[0], side(game, "white", game["white"]),
                       side(game, "black", game["black"]), str(game["year"]), ROOT / "out" / f"{game['id']}_cover.jpg")
    pkg = write_package(ROOT / "out" / "packages" / tag, video, cover, title, description, tags, when)
    info = {"package": str((ROOT / "out" / "packages" / tag).relative_to(ROOT))}
    if not remote:
        return info
    try:
        url = github_release(tag, f"#{number} {title.split(' | ')[0]} — {when}", pkg, ROOT)
        if url:
            info["release_url"] = url
            print(f"GitHub Release: {url}")
    except subprocess.CalledProcessError as e:
        print(f"::warning::GitHub Release nie powstał: {e.stderr.strip()[:300]}")
    try:
        info["telegram"] = telegram(pkg, title, when, info.get("release_url"))
    except Exception as e:  # noqa: BLE001 — Telegram to wygoda, nie blokuje odcinka
        print(f"::warning::Telegram: {e.__class__.__name__}: {str(e)[:200]}")
        info["telegram"] = False
    return info


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
        episode = produce(game, slot, args.no_upload, args.dry_tts, number=len(episodes) + 1)
        if args.dry_tts or (args.no_upload and MODE != "manual"):
            break  # test — bez zapisu stanu
        episodes.append(episode)
        if args.first_day and not state.get("first_day"):
            state["first_day"] = args.first_day
        save_json(STATE, state)  # zapis po każdym uploadzie — nie wgrywać drugi raz
        made += 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
