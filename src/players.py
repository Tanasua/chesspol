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


def catalog_entry(game_id: str) -> dict | None:
    if not CATALOG.exists():
        return None
    games = json.loads(CATALOG.read_text(encoding="utf-8")).get("games", [])
    return next((g for g in games if g["id"] == game_id), None)


def side(entry: dict | None, color: str, pgn_name: str) -> dict:
    """color: 'white'/'black'. Zwraca {name, first, last, photo, credit}."""
    e = entry or {}
    name = e.get(f"{color}_pl") or e.get(color) or pgn_name
    first, last = split_name(name)
    if e.get(f"{color}_first") is not None or e.get(f"{color}_last") is not None:
        first, last = e.get(f"{color}_first") or "", e.get(f"{color}_last") or name
    photo_key = slug(e.get(color) or pgn_name)  # zdjęcia po nazwie z bazy, nie po wersji polskiej
    jpg, meta = PHOTOS / f"{photo_key}.jpg", PHOTOS / f"{photo_key}.json"
    credit = json.loads(meta.read_text(encoding="utf-8")) if meta.exists() else None
    if credit and credit.get("author"):
        credit["author"] = " ".join(credit["author"].split())  # autor z Commons bywa wielowierszowy
    return {"name": name, "first": first, "last": last,
            "photo": jpg if jpg.exists() else None, "credit": credit}

