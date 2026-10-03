"""Kraj, który gracz reprezentował (Wikidata P1532 "country for sport", z datami), i jego oznaczenie w kadrze.

Flagi: assets/flags/<iso>.svg (flag-icons, MIT). Zamiast flag — tekstowy skrót (decyzja właściciela):
  Rosja / Imperium Rosyjskie / RFSRR -> "RU", Białoruś / BSRR -> "BY", ZSRR -> "SU", III Rzesza -> "DE".
Pliki ru.svg i by.svg celowo usunięte z assets/flags.
Pamięć podręczna: assets/players/countries.json {nazwa: {"qid":…, "periods": [{"code":…, "from":…, "to":…}]}}.
"""
from __future__ import annotations

import io
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLAGS = ROOT / "assets" / "flags"
CACHE = ROOT / "assets" / "players" / "countries.json"

TEXT_CODES = {"ru": "RU", "by": "BY", "su": "SU", "de-nazi": "DE"}
SPECIAL = {  # państwa bez kodu ISO albo z oznaczeniem tekstowym
    "Q15180": "su",      # ZSRR
    "Q7318": "de-nazi",  # III Rzesza
    "Q34266": "ru",      # Imperium Rosyjskie
    "Q2184": "ru",       # Rosyjska FSRR
    "Q159": "ru",        # Rosja
    "Q2895": "by",       # Białoruska SRR
    "Q184": "by",        # Białoruś
    "Q43287": "de",      # Cesarstwo Niemieckie -> flaga dzisiejszych Niemiec
    "Q41304": "de",      # Republika Weimarska
    "Q713750": "de",     # RFN (przed 1990)
    "Q16957": "de",      # NRD
    "Q33946": "cz",      # Czechosłowacja
    "Q36704": "rs",      # Jugosławia
    "Q83286": "rs",      # SFR Jugosławii
    "Q28513": "at",      # Austro-Węgry
    "Q207272": "pl",     # II Rzeczpospolita
    "Q170072": "nl",
}


def _load() -> dict:
    return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}


def _save(data: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _year(snak_value) -> int | None:
    m = re.match(r"[+-](\d{4})", (snak_value or {}).get("time", ""))
    return int(m.group(1)) if m else None


def _code_for(qid: str, api, wd_api: str, memo: dict) -> str | None:
    if qid in SPECIAL:
        return SPECIAL[qid]
    if qid not in memo:
        ent = api(wd_api, action="wbgetentities", ids=qid, props="claims")["entities"].get(qid, {})
        iso = [c["mainsnak"].get("datavalue", {}).get("value") for c in ent.get("claims", {}).get("P297", [])]
        memo[qid] = (iso[0] or "").lower() if iso else None
    return memo[qid]


def periods_from_entity(entity: dict, api, wd_api: str) -> list:
    """P1532 (reprezentowany kraj) z kwalifikatorami od/do; gdy brak — P27 (obywatelstwo)."""
    memo = {}
    out = []
    for prop in ("P1532", "P27"):
        for c in entity.get("claims", {}).get(prop, []):
            v = c.get("mainsnak", {}).get("datavalue", {}).get("value")
            if not isinstance(v, dict) or "id" not in v:
                continue
            code = _code_for(v["id"], api, wd_api, memo)
            if not code:
                continue
            q = c.get("qualifiers", {})
            start = _year((q.get("P580") or [{}])[0].get("datavalue", {}).get("value"))
            end = _year((q.get("P582") or [{}])[0].get("datavalue", {}).get("value"))
            out.append({"code": code, "from": start, "to": end, "prop": prop})
        if out:
            break
    return out


def remember(name: str, entity: dict, api, wd_api: str) -> list:
    data = _load()
    periods = periods_from_entity(entity, api, wd_api)
    data[name] = {"qid": entity.get("id"), "periods": periods}
    _save(data)
    return periods


def country(name: str, year: int | None = None) -> str | None:
    """Kod kraju gracza w danym roku (okres z datami obejmujący rok; inaczej ostatni bez daty końca)."""
    rec = _load().get(name)
    if not rec or not rec.get("periods"):
        return None
    ps = rec["periods"]
    if year:
        for p in ps:
            if (p["from"] or -9999) <= year <= (p["to"] or 9999) and (p["from"] or p["to"]):
                return p["code"]
    open_ended = [p for p in ps if not p["to"]]
    code = (open_ended or ps)[-1]["code"]
    if code == "de-nazi" and year and not 1933 <= year <= 1945:
        return "de"
    return code


def badge(code: str | None, height: int):
    """Obrazek RGBA: flaga (4:3) albo tekstowy skrót w ramce. None, gdy brak kodu/flagi."""
    from PIL import Image, ImageDraw

    if not code:
        return None
    w = round(height * 4 / 3)
    if code in TEXT_CODES:
        from render import _font

        img = Image.new("RGBA", (w, height), (34, 33, 31, 255))
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, w - 1, height - 1], outline=(170, 166, 158), width=max(1, height // 14))
        f = _font(int(height * 0.55), True)
        t = TEXT_CODES[code]
        d.text(((w - d.textlength(t, font=f)) / 2, (height - f.size) / 2 - height * 0.08), t, font=f,
               fill=(240, 236, 228))
        return img
    svg = FLAGS / f"{code}.svg"
    if not svg.exists():
        return None
    import cairosvg

    png = cairosvg.svg2png(url=str(svg), output_width=w, output_height=height)
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    ImageDraw.Draw(img).rectangle([0, 0, w - 1, height - 1], outline=(0, 0, 0, 90), width=1)
    return img
