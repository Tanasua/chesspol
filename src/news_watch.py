"""Autośledzenie turniejów: nowość na sobotę (rubryka "news", scheduler.RUBRIC_DAYS — decyzja właściciela 19.10.2026).

Działa tylko dla kanałów, których najbliższa wolna sobota zaczyna się w ciągu NEWS_LEAD_HOURS (domyślnie 36 h —
w praktyce przebieg w piątek wieczorem). Szuka rund ważnych turniejów z Lichess zakończonych w ostatnich 30 h,
a gdy brak — 7 dni, potem 30 dni (NEWS_WINDOWS); najważniejsza partia rundy (src/news.py --round-id --news-day).
Kanał hindi: tylko partia z Indusem (--require-home; news.py kod 3 = brak takiej, próbujemy następnej rundy).

Ważny turniej: poziom transmisji Lichess (tier) najwyższy albo nazwa z listy WATCH; bez tempa blitz/bullet/Freestyle.
Stan: state/news_watch.json {kanał: {"rounds": [id…], "last_day": "YYYY-MM-DD"}} — maks. 1 nowość na kanał dziennie,
każda runda raz. Kanał bez głosu (brak klucza TTS) jest pomijany.

  python src/news_watch.py            # wszystkie kanały
  python src/news_watch.py --dry      # tylko pokaż, co by zrobił
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
STATE = ROOT / "state" / "news_watch.json"
API = "https://lichess.org/api"
UA = {"User-Agent": "chesspol-news/1.0 (https://github.com/tanasua/chesspol)"}
WINDOWS = [timedelta(hours=int(h)) for h in os.environ.get("NEWS_WINDOWS", "30,168,720").split(",")]
LEAD = timedelta(hours=int(os.environ.get("NEWS_LEAD_HOURS", "36")))
MIN_LEAD = timedelta(hours=int(os.environ.get("MIN_LEAD_HOURS", "6")))
TRIES = int(os.environ.get("NEWS_TRIES", "4"))  # ile rund próbować na kanał (hindi: szukanie partii z Indusem)
WATCH = re.compile(r"world championship|candidates|tata steel|norway chess|grand chess tour|sinquefield|superbet|"
                   r"olympiad|world cup|grand swiss|london chess classic|gibraltar|dortmund|shamkir|chessable masters",
                   re.I)
# kanał hindi: turnieje indyjskie (także niższy tier) i pierwszeństwo przed resztą (decyzja właściciela: skupić się na Indiach)
INDIA = re.compile(r"india|indian|chennai|kolkata|mumbai|delhi|bengaluru|bangalore|global chess league|tata steel india|"
                   r"india.{0,30}national|national.{0,30}india", re.I)
SKIP = re.compile(r"blitz|bullet|freestyle|chess960|titled|armageddon|junior|youth|women'?s rapid|u\d\d", re.I)
CHANNELS = {  # kanał -> zmienne z kluczem i głosem TTS (bez nich kanał pomijamy)
    "pl": ("INWORLD_API_KEY", "INWORLD_VOICE_ID", None),
    "de": ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID_DE", "ELEVENLABS_VOICE_ID"),
    "en": ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID_EN", "ELEVENLABS_VOICE_ID"),
    "hi": ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID_HI", "ELEVENLABS_VOICE_ID"),
    "uk": ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID_UA", "ELEVENLABS_VOICE_ID"),
    "ru": ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID_RU", "ELEVENLABS_VOICE_ID"),
    "tr": ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID_TR", "ELEVENLABS_VOICE_ID"),
}


def _get(url: str, **kw):
    for attempt in range(4):
        r = requests.get(url, headers=UA, timeout=60, **kw)
        if r.status_code == 429:
            time.sleep(60)
            continue
        if r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()


def _ts(ms) -> datetime | None:
    return datetime.fromtimestamp(ms / 1000, timezone.utc) if ms else None


def news_due(ch: str, now: datetime):
    """Najbliższa sobota bez odcinka w harmonogramie kanału, jeśli zaczyna się (18:00 lokalnie) w ciągu LEAD."""
    from zoneinfo import ZoneInfo
    from lang import CHANNELS as LC
    c = LC[ch]
    tz = ZoneInfo(c.tz)
    eps = json.loads(c.state.read_text(encoding="utf-8")).get("episodes", []) if c.state.exists() else []
    booked = {datetime.fromisoformat(e["publish_at"]).astimezone(tz).date() for e in eps if e.get("publish_at")}
    day = (now + MIN_LEAD).astimezone(tz).date()
    while day.weekday() != 5 or day in booked:
        day += timedelta(days=1)
    start = datetime(day.year, day.month, day.day, 18, tzinfo=tz)
    return day if start - now <= LEAD else None


def finished_rounds(now: datetime, window: timedelta) -> list:
    """[(waga, tour, round)] — rundy zakończone w oknie `window`, ważne turnieje, od najważniejszej."""
    data = _get(f"{API}/broadcast/top", params={"page": 1}).json()
    entries = list(data.get("active", [])) + list((data.get("past") or {}).get("currentPageResults", []))
    for page in range(2, 2 + min(4, int(window / timedelta(days=7)))):  # dłuższe okno — starsze strony "past"
        try:
            more = _get(f"{API}/broadcast/top", params={"page": page}).json()
        except requests.HTTPError:
            break
        entries += list((more.get("past") or {}).get("currentPageResults", []))
    print("Lichess top — klucze:", sorted(data.keys()), "| pozycji:", len(entries))
    for e in entries[:25]:
        t, r = e.get("tour", {}), e.get("round", {})
        print(f"    tier={t.get('tier')} {t.get('name')!r} | ostatnia runda: {r.get('name')!r} "
              f"finished={r.get('finished')} startsAt={r.get('startsAt')} finishedAt={r.get('finishedAt')}")
    out, seen = [], set()
    for e in entries:
        tour = e.get("tour", {})
        name = tour.get("name", "")
        if not name or SKIP.search(name) or tour.get("id") in seen:
            continue
        tier = int(tour.get("tier") or 0)
        watched = bool(WATCH.search(name))
        india = bool(INDIA.search(name))
        if not watched and tier < 5 and not india:
            continue
        seen.add(tour.get("id"))
        try:
            full = _get(f"{API}/broadcast/{tour['id']}").json()
        except requests.HTTPError:
            continue
        for rnd in full.get("rounds", []):
            done = bool(rnd.get("finished") or rnd.get("finishedAt"))
            when = _ts(rnd.get("finishedAt")) or (_ts(rnd.get("startsAt")) + timedelta(hours=6) if rnd.get("startsAt") else None)
            if done and when and now - window <= when <= now:
                weight = tier * 10 + (5 if watched else 0) + (3 if re.search(r"final|world championship", name, re.I) else 0)
                tour = dict(tour, _india=india, _main=watched or tier >= 5)
                out.append((weight, tour, rnd))
    out.sort(key=lambda x: -x[0])
    for w, t, r in out:
        print(f"  {w:3}  {t.get('name')} — {r.get('name')} ({r.get('id')})")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--force", action="store_true", help="bez warunku 'sobota w ciągu NEWS_LEAD_HOURS'")
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    cache: dict = {}
    rc = 0
    for ch, (key_env, voice_env, target_env) in CHANNELS.items():
        st = state.setdefault(ch, {"rounds": [], "last_day": ""})
        if not (os.environ.get(key_env) and os.environ.get(voice_env)):
            print(f"[{ch}] pominięty — brak {key_env}/{voice_env}")
            continue
        day = news_due(ch, now)
        if not day and not args.force:
            print(f"[{ch}] najbliższa wolna sobota jeszcze nie teraz — czekam")
            continue
        print(f"[{ch}] nowość na {day}")
        made = False
        for window in WINDOWS:
            if window not in cache:
                print(f"Zakończone rundy ważnych turniejów (ostatnie {window}):")
                cache[window] = finished_rounds(now, window)
            # hindi: najpierw ważne turnieje (partia z Indusem — --require-home), potem turnieje indyjskie niższej rangi
            todo = [(w + (100 if ch == "hi" and t.get("_main") else 0), t, r) for w, t, r in cache[window]
                    if r.get("id") not in st["rounds"] and (t.get("_main") or ch == "hi")]
            todo = [(t, r) for _, t, r in sorted(todo, key=lambda x: -x[0])]
            for tour, rnd in todo[:TRIES]:
                print(f"[{ch}] próba: {tour.get('name')} — {rnd.get('name')} (okno {window})")
                if args.dry:
                    made = True
                    break
                env = {**os.environ, "CHANNEL": ch}
                if target_env:
                    env[target_env] = os.environ[voice_env]
                cmd = [sys.executable, str(ROOT / "src" / "news.py"), "--tournament", tour["id"],
                       "--round-id", rnd["id"], "--news-day"] + (["--require-home"] if ch == "hi" else [])
                r = subprocess.run(cmd, cwd=ROOT, env=env)
                if r.returncode == 3:  # w tej rundzie nic dla kanału (np. bez Indusa) — następna
                    continue
                if r.returncode != 0:
                    print(f"::error::[{ch}] news.py zakończył się kodem {r.returncode}")
                    rc = 1
                    continue
                st["rounds"] = (st["rounds"] + [rnd["id"]])[-200:]
                st["last_day"] = today
                STATE.parent.mkdir(parents=True, exist_ok=True)
                STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                made = True
                break
            if made:
                break
        if not made:
            print(f"::warning::[{ch}] brak nowości nawet z {WINDOWS[-1]} — sobotę wypełni scheduler (zastępstwo)")
    return rc


if __name__ == "__main__":
    sys.exit(main())
