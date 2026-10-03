"""Autośledzenie turniejów (codziennie): jeśli w ciągu ostatniej doby zakończyła się runda ważnego turnieju
transmitowanego na Lichess — jedna nowość na kanał (najważniejsza partia tej rundy, src/news.py --round-id).

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
WINDOW = timedelta(hours=int(os.environ.get("NEWS_WINDOW_HOURS", "30")))
WATCH = re.compile(r"world championship|candidates|tata steel|norway chess|grand chess tour|sinquefield|superbet|"
                   r"olympiad|world cup|grand swiss|london chess classic|gibraltar|dortmund|shamkir|chessable masters",
                   re.I)
SKIP = re.compile(r"blitz|bullet|freestyle|chess960|titled|armageddon|junior|youth|women'?s rapid|u\d\d", re.I)
CHANNELS = {  # kanał -> zmienne z kluczem i głosem TTS (bez nich kanał pomijamy)
    "pl": ("INWORLD_API_KEY", "INWORLD_VOICE_ID", None),
    "de": ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID_DE", "ELEVENLABS_VOICE_ID"),
    "en": ("ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID_EN", "ELEVENLABS_VOICE_ID"),
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


def finished_rounds(now: datetime) -> list:
    """[(waga, tour, round)] — rundy zakończone w oknie WINDOW, ważne turnieje, od najważniejszej."""
    data = _get(f"{API}/broadcast/top", params={"page": 1}).json()
    entries = list(data.get("active", [])) + list((data.get("past") or {}).get("currentPageResults", []))
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
        if not watched and tier < 5:
            continue
        seen.add(tour.get("id"))
        try:
            full = _get(f"{API}/broadcast/{tour['id']}").json()
        except requests.HTTPError:
            continue
        for rnd in full.get("rounds", []):
            done = bool(rnd.get("finished") or rnd.get("finishedAt"))
            when = _ts(rnd.get("finishedAt")) or (_ts(rnd.get("startsAt")) + timedelta(hours=6) if rnd.get("startsAt") else None)
            if done and when and now - WINDOW <= when <= now:
                weight = tier * 10 + (5 if watched else 0) + (3 if re.search(r"final|world championship", name, re.I) else 0)
                out.append((weight, tour, rnd))
    out.sort(key=lambda x: -x[0])
    for w, t, r in out:
        print(f"  {w:3}  {t.get('name')} — {r.get('name')} ({r.get('id')})")
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    now = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    state = json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}
    print("Zakończone rundy ważnych turniejów (ostatnie", WINDOW, "):")
    rounds = finished_rounds(now)
    if not rounds:
        print("Brak — dziś bez nowości.")
        return 0
    rc = 0
    for ch, (key_env, voice_env, target_env) in CHANNELS.items():
        st = state.setdefault(ch, {"rounds": [], "last_day": ""})
        if not (os.environ.get(key_env) and os.environ.get(voice_env)):
            print(f"[{ch}] pominięty — brak {key_env}/{voice_env}")
            continue
        if st["last_day"] == today:
            print(f"[{ch}] dziś już była nowość")
            continue
        todo = [(t, r) for _, t, r in rounds if r.get("id") not in st["rounds"]]
        if not todo:
            print(f"[{ch}] wszystkie rundy już omówione")
            continue
        tour, rnd = todo[0]
        print(f"[{ch}] nowość: {tour.get('name')} — {rnd.get('name')}")
        if args.dry:
            continue
        env = {**os.environ, "CHANNEL": ch}
        if target_env:
            env[target_env] = os.environ[voice_env]
        r = subprocess.run([sys.executable, str(ROOT / "src" / "news.py"), "--tournament", tour["id"],
                            "--round-id", rnd["id"]], cwd=ROOT, env=env)
        if r.returncode != 0:
            print(f"::error::[{ch}] news.py zakończył się kodem {r.returncode}")
            rc = 1
            continue
        st["rounds"] = (st["rounds"] + [rnd["id"]])[-200:]
        st["last_day"] = today
        STATE.parent.mkdir(parents=True, exist_ok=True)
        STATE.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return rc


if __name__ == "__main__":
    sys.exit(main())
