"""Dane o graczach do kadru: nazwa do wyświetlenia, zdjęcie i jego atrybucja.

Zdjęcia: assets/players/<slug>.jpg + <slug>.json (autor, licencja, adres strony pliku).
Pobiera je src/fetch_portraits.py (Wikidata P18 -> Wikimedia Commons, tylko wolne licencje).
Brak zdjęcia -> w kadrze inicjały.
"""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog" / "games.json"
PHOTOS = ROOT / "assets" / "players"

PARTICLES = {"de", "la", "von", "van", "der", "den", "di", "da", "le"}


def slug(name: str) -> str:
    s = unicodedata.normalize("NFKD", name)
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "_", s).strip("_")


def split_name(name: str) -> tuple[str, str]:
    """('José Raúl', 'Capablanca'), ('Louis-Charles Mahé', 'de La Bourdonnais')."""
    words = name.split()
    if len(words) < 2:
        return "", name
    i = len(words) - 1
    while i > 1 and words[i - 1].lower() in PARTICLES:
        i -= 1
    return " ".join(words[:i]), " ".join(words[i:])


NEWS = ROOT / "catalog" / "news.json"  # partie z bieżących turniejów (src/news.py)


def catalog_entry(game_id: str) -> dict | None:
    for path in (CATALOG, NEWS):
        if path.exists():
            games = json.loads(path.read_text(encoding="utf-8")).get("games", [])
            hit = next((g for g in games if g["id"] == game_id), None)
            if hit:
                return hit
    return None


def photo_path(name: str) -> Path | None:
    """Zdjęcie po pełnej nazwie; gdy brak — jedyne zdjęcie z tym samym nazwiskiem (np. 'R Praggnanandhaa'
    -> rameshbabu_praggnanandhaa.jpg). Przy kilku kandydatach nie zgadujemy."""
    jpg = PHOTOS / f"{slug(name)}.jpg"
    if jpg.exists():
        return jpg
    last = slug(split_name(name)[1] or name)
    hits = [p for p in PHOTOS.glob("*.jpg") if p.stem == last or p.stem.endswith("_" + last)]
    qids = set()
    for h in hits:  # kilka plików tej samej osoby (ten sam QID w Wikidata) — to wciąż jednoznaczne
        meta = h.with_suffix(".json")
        qids.add(json.loads(meta.read_text(encoding="utf-8")).get("qid") if meta.exists() else h.stem)
    return sorted(hits)[0] if hits and len(qids) == 1 else None


def side(entry: dict | None, color: str, pgn_name: str) -> dict:
    """color: 'white'/'black'. Zwraca {name, first, last, photo, credit}."""
    from lang import field_

    e = entry or {}
    name = field_(e, color) or pgn_name  # white_pl / white_de, w razie braku — nazwa bazowa
    first, last = split_name(name)
    if field_(e, f"{color}_first") is not None or field_(e, f"{color}_last") is not None:
        first, last = field_(e, f"{color}_first") or "", field_(e, f"{color}_last") or name
    jpg = photo_path(e.get(color) or pgn_name) or PHOTOS / "_brak_.jpg"  # po nazwie z bazy, nie po wersji językowej
    meta = jpg.with_suffix(".json")
    credit = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else None
    if credit and credit.get("author"):
        credit["author"] = " ".join(credit["author"].split())  # autor z Commons bywa wielowierszowy
    return {"name": name, "first": first, "last": last,
            "photo": jpg if jpg.exists() else None, "credit": credit}

