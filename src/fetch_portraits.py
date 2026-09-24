"""Pobiera zdjęcia graczy z katalogu: Wikidata (P18) -> Wikimedia Commons, tylko wolne licencje.

  python src/fetch_portraits.py            # brakujące zdjęcia
  python src/fetch_portraits.py --force    # od nowa

Wynik: assets/players/<slug>.jpg + <slug>.json (qid, plik, autor, licencja, adres strony pliku)
oraz assets/players/REPORT.md — lista do przejrzenia przez człowieka (czy to właściwa osoba).
Ręczne poprawki: assets/players/overrides.json {"Imię Nazwisko": "Q123"} albo {"Imię Nazwisko": null} (bez zdjęcia).

Akceptowane licencje: domena publiczna, CC0, CC BY, CC BY-SA. Odrzucane: NC, ND, GFDL-only, brak licencji.
Dopasowanie osoby: zawód P106 = szachista (Q10873124), nazwa/alias zgodne z katalogiem, rok urodzenia
spójny z latami partii. W razie wątpliwości — brak zdjęcia (w kadrze inicjały), nie zgadujemy.
"""
from __future__ import annotations

import argparse
import html
import io
import json
import re
import sys
import time
from pathlib import Path

import requests
from PIL import Image

from players import CATALOG, PHOTOS, slug
from pgn_collect import norm

WD_API = "https://www.wikidata.org/w/api.php"
COMMONS_API = "https://commons.wikimedia.org/w/api.php"
CHESS_PLAYER = "Q10873124"
UA = "chesspol-portraits/1.0 (https://github.com/tanasua/chesspol; YouTube chess history channel)"
NOT_PEOPLE = {"Deep Blue", "Deep Fritz", "AlphaZero", "Stockfish 8", "The World",
              "Duke Karl of Brunswick & Count Isouard", "Glücksberg"}
LICENSE_OK = re.compile(r"^(public domain|pd\b|cc0|cc[- ]by(-sa)?[- ][\d.]+)", re.I)
LICENSE_BAD = re.compile(r"\b(nc|nd)\b|noncommercial|noderivs", re.I)

session = requests.Session()
session.headers["User-Agent"] = UA


def api(url: str, **params) -> dict:
    params["format"] = "json"
    for attempt in range(4):
        r = session.get(url, params=params, timeout=30)
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        time.sleep(0.2)
        return r.json()
    r.raise_for_status()
    return {}


def players_with_years(catalog: dict) -> dict:
    out = {}
    for g in catalog["games"]:
        for color in ("white", "black"):
            name = g[color]
            if name in NOT_PEOPLE:
                continue
            ys = out.setdefault(name, [])
            ys.append(int(g["year"]))
    return out


def _claim_ids(entity: dict, prop: str) -> list:
    vals = []
    for c in entity.get("claims", {}).get(prop, []):
        v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
        if isinstance(v, dict) and "id" in v:
            vals.append(v["id"])
        elif isinstance(v, str):
            vals.append(v)
    return vals


def _birth_year(entity: dict) -> int | None:
    for c in entity.get("claims", {}).get("P569", []):
        t = c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("time", "")
        m = re.match(r"[+-](\d{4})", t)
        if m:
            return int(m.group(1))
    return None


def find_person(name: str, years: list, override: str | None) -> tuple[dict | None, str]:
    if override:
        ents = api(WD_API, action="wbgetentities", ids=override, props="claims|labels|aliases")["entities"]
        return ents.get(override), "ręcznie (overrides.json)"
    hits = api(WD_API, action="wbsearchentities", search=name, language="en", type="item", limit=7).get("search", [])
    if not hits:
        return None, "brak wyników w Wikidata"
    ents = api(WD_API, action="wbgetentities", ids="|".join(h["id"] for h in hits),
               props="claims|labels|aliases", languages="en|pl|de|fr|es|ru")["entities"]
    target = norm(name).split()
    for h in hits:  # kolejność wyszukiwarki
        e = ents.get(h["id"], {})
        if CHESS_PLAYER not in _claim_ids(e, "P106"):
            continue
        names = [v["value"] for v in e.get("labels", {}).values()]
        names += [a["value"] for al in e.get("aliases", {}).values() for a in al]
        # tylko pełna zgodność imienia i nazwiska z etykietą lub aliasem (np. Emanuel ≠ Edward Lasker)
        if not any(norm(n).split() == target for n in names):
            continue
        by = _birth_year(e)
        if by is not None and not (min(years) - 85 <= by <= min(years) - 8):
            continue
        return e, f"auto ({h['id']})"
    return None, "nie znaleziono szachisty o tej nazwie (sprawdź overrides.json)"


def commons_file(filename: str) -> dict | None:
    data = api(COMMONS_API, action="query", titles=f"File:{filename}", prop="imageinfo",
               iiprop="url|extmetadata", iiurlwidth=600)
    for page in data.get("query", {}).get("pages", {}).values():
        info = (page.get("imageinfo") or [None])[0]
        if not info:
            return None
        meta = info.get("extmetadata", {})
        get = lambda k: html.unescape(re.sub(r"<[^>]+>", "", meta.get(k, {}).get("value", ""))).strip()
        return {"file": filename, "thumb": info.get("thumburl") or info.get("url"),
                "source_url": info.get("descriptionurl"), "author": get("Artist") or None,
                "license": get("LicenseShortName"), "license_url": get("LicenseUrl") or None}
    return None


def license_ok(lic: str) -> bool:
    return bool(lic) and bool(LICENSE_OK.match(lic)) and not LICENSE_BAD.search(lic)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    PHOTOS.mkdir(parents=True, exist_ok=True)
    ov_path = PHOTOS / "overrides.json"
    overrides = json.loads(ov_path.read_text(encoding="utf-8")) if ov_path.exists() else {}
    report = ["# Zdjęcia graczy", "", "Sprawdź, czy zdjęcie przedstawia właściwą osobę. Poprawki: overrides.json.", "",
              "| Gracz | Status | Wikidata | Licencja | Autor |", "|---|---|---|---|---|"]
    ok = 0
    for name, years in sorted(players_with_years(catalog).items()):
        key = slug(name)
        jpg, meta_path = PHOTOS / f"{key}.jpg", PHOTOS / f"{key}.json"
        if jpg.exists() and meta_path.exists() and not args.force:
            m = json.loads(meta_path.read_text(encoding="utf-8"))
            report.append(f"| {name} | ✅ (już jest) | {m.get('qid','')} | {m.get('license','')} | {m.get('author') or ''} |")
            ok += 1
            continue
        if name in overrides and overrides[name] is None:
            report.append(f"| {name} | pominięty (overrides) | | | |")
            continue
        try:
            person, how = find_person(name, years, overrides.get(name))
            if not person:
                report.append(f"| {name} | brak: {how} | | | |")
                continue
            files = _claim_ids(person, "P18")
            if not files:
                report.append(f"| {name} | brak zdjęcia w Wikidata | {person['id']} | | |")
                continue
            info = commons_file(files[0])
            if not info or not license_ok(info["license"]):
                report.append(f"| {name} | licencja odrzucona | {person['id']} | {info and info['license']} | |")
                continue
            r = session.get(info["thumb"], timeout=60)
            r.raise_for_status()
            Image.open(io.BytesIO(r.content)).convert("RGB").save(jpg, "JPEG", quality=88)
            info.update(qid=person["id"], name=name, matched=how)
            info.pop("thumb", None)
            meta_path.write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            report.append(f"| {name} | ✅ {how} | {person['id']} | {info['license']} | {info['author'] or ''} |")
            ok += 1
        except requests.RequestException as e:
            report.append(f"| {name} | błąd sieci: {e.__class__.__name__} | | | |")
    total = len(players_with_years(catalog))
    report += ["", f"Zdjęcia: **{ok}/{total}** graczy."]
    (PHOTOS / "REPORT.md").write_text("\n".join(report) + "\n", encoding="utf-8")
    print(f"Zdjęcia: {ok}/{total}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
