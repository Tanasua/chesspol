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
  python src/scheduler.py --dry-tts     # jak --no-upload, ale bez TTS (cisza)
  CHANNEL=de python src/scheduler.py    # kanał niemiecki: kolejność n_de, state/schedule_de.json, scripts_de/

Kanały (src/lang.py) mają wspólny katalog, ale każdy własną kolejność, stan i scenariusze.
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

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lang import NATIONAL, L, field_, moves_word  # noqa: E402
from phrases import title_hook_for  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
CATALOG = ROOT / "catalog" / "games.json"
STATE = L.state

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
    games = [g for g in catalog["games"] if isinstance(g.get(L.order_key), int)]
    return [g for g in sorted(games, key=lambda g: g[L.order_key]) if g["id"] not in done and ready(g)]


WEEKDAYS_UK = ["пн", "вт", "ср", "чт", "пт", "сб", "нд"]


def when_uk(dt: datetime) -> str:
    """Data publikacji dla właściciela, po ukraińsku: 'пт, 02.10.2026 о 10:00 (за Києвом)'."""
    loc = dt.astimezone(TZ)
    if TZ.key == "Europe/Kyiv":
        return f"{WEEKDAYS_UK[loc.weekday()]}, {loc:%d.%m.%Y} о {loc:%H:%M} (за Києвом)"
    kyiv = dt.astimezone(ZoneInfo("Europe/Kyiv"))  # канал для іншого ринку: місцевий час + київський
    city = {"America/New_York": "Нью-Йорком", "Europe/Berlin": "Берліном", "Europe/Warsaw": "Варшавою"}.get(TZ.key, TZ.key)
    return (f"{WEEKDAYS_UK[loc.weekday()]}, {loc:%d.%m.%Y} о {loc:%H:%M} (за {city}) = "
            f"{WEEKDAYS_UK[kyiv.weekday()]} {kyiv:%H:%M} за Києвом")


def national_queue(national: dict, episodes: list) -> list:
    """Rubryka krajowa: partie najsłynniejszych szachistów kraju kanału (catalog/national_<kraj>.json, pole n)."""
    done = {e["id"] for e in episodes}
    return [g for g in sorted(national.get("games", []), key=lambda g: g.get("n", 999))
            if g["id"] not in done and ready(g)]


def pick(episodes: list, q: list, nq: list) -> tuple[str, dict | None]:
    """Na przemian: historia -> rubryka krajowa -> historia… Gdy jednej kolejki brak — druga."""
    last = episodes[-1].get("rubric", "history") if episodes else "national"
    order = ("national", "history") if last == "history" else ("history", "national")
    for rubric in order:
        src = nq if rubric == "national" else q
        if src:
            return rubric, src.pop(0)
    return "", None


def run(cmd: list) -> None:
    print("$", " ".join(cmd), flush=True)
    subprocess.run(cmd, check=True, cwd=ROOT)


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


def _yt_title(main: str, white: str, black: str, game: dict, hook: str = "") -> str:
    """Tytuł YouTube (maks. 100 znaków): '<dopisek>: <tytuł> | Nazwisko – Nazwisko (rok)'.
    Tylko nazwiska (w pisowni języka kanału) — na telefonie widać ~40 pierwszych znaków; gdy za długo — bez dopisku,
    na końcu skracamy tytuł."""
    who = f"{white} – {black} ({game['year']})"
    heads = [f"{hook}: {main}" if hook and main else (hook or main)]
    if hook and main:
        heads.append(main)
    for head in heads:
        t = f"{head} | {who}" if head else who
        if len(t) <= 100:
            return t
    suffix = f" | {who}"
    return f"{main[:100 - len(suffix) - 1].rstrip()}…{suffix}"


def describe(game: dict, script: dict, pgn: Path | None = None, timing: dict | None = None) -> tuple[str, str, list]:
    t = L.t
    white, black = field_(game, "white"), field_(game, "black")
    place = field_(game, "site") or ""
    label = (field_(game, "label") or field_(game, "event") or "").replace(" · ", ", ")
    from players import side

    ws, bs = side(game, "white", white)["last"], side(game, "black", black)["last"]
    kicker = (script.get("kicker") or "").strip()
    if kicker:  # nowe scenariusze: "NIESAMOWITE! <tytuł>" zamiast stałego dopisku
        title = _yt_title(f"{kicker} {script.get('title') or ''}".strip(), ws, bs, game)
    else:
        title = _yt_title(script.get("title") or "", ws, bs, game, title_hook_for(game))

    lines = []
    if script.get("description"):
        lines += [script["description"].strip(), ""]
    lines += [f"{t['white']}: {white}", f"{t['black']}: {black}",
              f"{t['year']}: {game['year']}" + (f" · {place}" if place else ""), label]
    n_moves = 0
    if pgn and pgn.exists():
        import chess.pgn
        with open(pgn, encoding="utf-8") as fh:
            g = chess.pgn.read_game(fh)
        n_moves = (sum(1 for _ in g.mainline_moves()) + 1) // 2
    if game.get("result"):
        lines.append(f"{t['result']}: {game['result']}" + (f" ({n_moves} {moves_word(n_moves)})" if n_moves else ""))

    chapters = _chapters(timing or {})
    if chapters:
        lines += ["", t["chapters"]] + [f"{_ts(c['t'])} {c['title']}" for c in chapters]
    # bez zapisu ruchów i bez listy źródeł zdjęć (decyzja właściciela); autor i licencja zdjęcia są w kadrze
    if game.get("pgn_verified"):
        lines += ["", t["verified"].strip()]
    lines += ["", f"{t['hashtags']} #{game['white'].split()[-1]} #{game['black'].split()[-1]}"]
    description = "\n".join(lines).strip()[:4900]  # limit YouTube: 5000 znaków
    tags = [*t["tags"], white.split()[-1], black.split()[-1], t["year_tag"].format(year=game["year"])]
    return title, description, tags


def produce(game: dict, publish_at: datetime, no_upload: bool, dry_tts: bool = False, number: int = 1) -> dict:
    gid = game["id"]
    pgn = ROOT / "games" / f"{gid}.pgn"
    script_path = L.scripts / f"{gid}.json"
    video = L.out / f"{gid}.mp4"
    py = sys.executable

    if not script_path.exists():
        run([py, str(SRC / "script_gen.py"), "--pgn", str(pgn), "--out", str(script_path), "--name", gid])
    run([py, str(SRC / "main.py"), "--pgn", str(pgn), "--script", str(script_path), "--out", str(video)]
        + (["--dry-run"] if dry_tts else []))

    script = load_json(script_path, {})
    title, description, tags = describe(game, script, pgn, load_json(video.with_suffix(".timing.json"), {}))
    when = when_uk(publish_at)
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
                    when: str, number: int, remote: bool = True, tag: str | None = None, badge: str = "",
                    preroll: Path | None = None) -> dict:
    from cover import make_cover
    from deliver import github_release, telegram, write_package
    from pgn_loader import load_game
    from players import side

    g = load_game(pgn)
    tag = tag or f"{L.tag_prefix}ep{number:03d}-{game['id']}"
    from cover_marks import compute as cover_marks

    try:
        marks = cover_marks(g, seed=number or game["id"])
        print("Okładka — znaki:", "; ".join(marks.notes) or "strzałka ostatniego ruchu", f"[{marks.glyph or '-'}]")
    except Exception as e:  # noqa: BLE001 — strzałki to ozdoba, nie blokują odcinka
        print(f"::warning::Okładka — strzałki: {e.__class__.__name__}: {str(e)[:200]}")
        marks = None
    cover = make_cover(g, title.split(" | ")[0], side(game, "white", game["white"]),
                       side(game, "black", game["black"]), str(game["year"]), L.out / f"{game['id']}_cover.jpg",
                       badge=badge, marks=marks)
    from cover_ai import enabled as ai_enabled, make_ai_cover
    ai_cover, ai_note = (make_ai_cover(cover, cover.with_name(f"{game['id']}_cover_ai.jpg"))
                         if remote and ai_enabled() else (None, ""))
    if ai_cover:
        print(f"Okładka OpenAI: {ai_cover} ({ai_note})")
    elif ai_note:
        print(f"::warning::Okładka OpenAI: {ai_note[:300]}")
    pkg = write_package(ROOT / "out" / "packages" / tag, video, cover, title, description, tags, when,
                        ai_cover=ai_cover, ai_note=ai_note)
    info = {"package": str((ROOT / "out" / "packages" / tag).relative_to(ROOT))}
    if not remote:
        return info
    try:
        url = github_release(tag, f"{L.flag} #{number} {title.split(' | ')[0]} — {when}", pkg, ROOT)
        if url:
            info["release_url"] = url
            print(f"GitHub Release: {url}")
    except subprocess.CalledProcessError as e:
        print(f"::warning::GitHub Release nie powstał: {e.stderr.strip()[:300]}")
    try:
        info["telegram"] = telegram(pkg, title, when, info.get("release_url"), number)
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
    ap.add_argument("--game", help="id partii na najbliższy odcinek (z katalogu głównego albo krajowego), poza kolejką")
    args = ap.parse_args()
    if args.dry_tts:
        args.no_upload = True

    catalog = load_json(CATALOG, {"games": []})
    national = load_json(NATIONAL, {"games": []})
    state = load_json(STATE, {"episodes": []})
    episodes = state["episodes"]
    now = datetime.now(timezone.utc)
    first_day = date.fromisoformat(args.first_day or state.get("first_day") or "") \
        if (args.first_day or state.get("first_day")) else None

    q = queue(catalog, episodes)
    nq = national_queue(national, episodes)
    print(f"Kolejka: historia {len(q)}, rubryka krajowa ({NATIONAL.name}) {len(nq)}")
    if len(q) < LOW_QUEUE_WARN:
        print(f"::warning::W kolejce tylko {len(q)} gotowych partii (PGN zweryfikowane)")

    if args.plan:
        eps = list(episodes)
        q2, nq2 = list(q), list(nq)
        for _ in range(10):
            rubric, g = pick(eps, q2, nq2)
            if not g:
                break
            slot = next_slot(eps, now, first_day)
            print(f"{slot.astimezone(TZ):%Y-%m-%d %H:%M %Z}  [{L.code}] {rubric:8} {g['id']}")
            eps.append({"id": g["id"], "publish_at": slot.isoformat(), "rubric": rubric})
        return 0

    made = 0
    while made < MAX_PER_RUN:
        future = [e for e in episodes if datetime.fromisoformat(e["publish_at"]) > now]
        if len(future) >= BUFFER:
            print(f"Zaplanowane naprzód: {len(future)} (bufor {BUFFER}) — nic do zrobienia")
            break
        forced = None
        if args.game and made == 0:  # wybór właściciela na najbliższy odcinek
            for rub, src in (("history", q), ("national", nq)):
                forced = next((g for g in src if g["id"] == args.game), None)
                if forced:
                    src.remove(forced)
                    rubric, game = rub, forced
                    break
            if not forced:
                print(f"::error::Partii {args.game} nie ma w kolejce (brak zweryfikowanego PGN albo już była)")
                return 1
        if not forced:
            rubric, game = pick(episodes, q, nq)
        if not game:
            print("::error::Brak gotowych partii — dodaj zweryfikowane PGN (src/pgn_collect.py)")
            return 1
        slot = next_slot(episodes, now, first_day)
        episode = produce(game, slot, args.no_upload, args.dry_tts, number=len(episodes) + 1)
        episode["rubric"] = rubric
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
