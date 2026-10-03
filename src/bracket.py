"""Plansza na początek odcinka-nowości (1920x1080): drabinka pucharowa albo tabela turnieju kołowego.

Stan PRZED pokazywaną partią: wyniki meczów liczone z partii rozegranych wcześniej, odpadli przekreśleni
(tylko z meczów zakończonych przed tą partią), mecz z tą partią wyróżniony ramką i napisem "TA PARTIA".
"""
from __future__ import annotations

import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from lang import L
from players import PHOTOS, slug, split_name
from render import ACCENT, BG, CARD, DIM, FG, H, W, _fit, _font

MINI = (84, 104)
RED = (215, 70, 60)


def _mini(name: str, out: bool) -> Image.Image:
    from players import photo_path

    jpg = photo_path(name)
    if jpg:
        img = ImageOps.fit(Image.open(jpg).convert("RGB"), MINI, centering=(0.5, 0.3))
        if out:
            img = ImageOps.grayscale(img).convert("RGB").point(lambda v: int(v * 0.55))
        return img
    img = Image.new("RGB", MINI, CARD)
    d = ImageDraw.Draw(img)
    first, last = split_name(name)
    ini = "".join(w[0] for w in f"{first} {last}".split()[:2] if w[:1].isalpha()).upper()
    f = _font(34, True)
    d.text(((MINI[0] - d.textlength(ini, font=f)) / 2, MINI[1] / 2 - 22), ini, font=f, fill=DIM)
    return img


def _player_row(img: Image.Image, d: ImageDraw.ImageDraw, x: int, y: int, w: int, name: str,
                score: str, out: bool, winner: bool) -> None:
    img.paste(_mini(name, out), (x, y))
    from news import surname

    from countries import badge, country

    last = surname(name).upper()
    tx = x + MINI[0] + 18
    fl = badge(country(name), 30)
    if fl:  # flaga przed nazwiskiem
        if out:  # odpadły — przygaszona flaga
            fl = Image.blend(Image.new("RGBA", fl.size, (34, 33, 31, 255)), fl, 0.45)
        img.paste(fl, (tx, int(y + MINI[1] / 2 - 15)), fl)
        tx += fl.width + 14
    f = _fit(d, last, 38, x + w - 110 - tx, True)
    col = DIM if out else FG
    d.text((tx, y + MINI[1] / 2 - f.size / 2 - 4), last, font=f, fill=col)
    if out:  # przekreślenie odpadłego: nazwisko i portret
        tw = d.textlength(last, font=f)
        ym = y + MINI[1] / 2
        d.line([tx - 4, ym, tx + tw + 4, ym], fill=RED, width=5)
        d.line([x, y, x + MINI[0], y + MINI[1]], fill=RED, width=4)
    sf = _font(40, True)
    d.text((x + w - d.textlength(score, font=sf) - 12, y + MINI[1] / 2 - 26), score,
           font=sf, fill=ACCENT if winner else (DIM if out else FG))


def _box(img, d, x, y, w, m, pick, matches) -> int:
    from news import stage_name

    current = pick in m.games
    done = m.finished_before(pick.seq)
    sa, sb = m.score(pick.seq)
    win = m.winner() if done else None
    loser = (m.b if win == m.a else m.a) if win else None
    h = 2 * MINI[1] + 3 * 14 + 44
    d.rounded_rectangle([x, y, x + w, y + h], radius=14, fill=CARD,
                        outline=ACCENT if current else (60, 58, 55), width=5 if current else 2)
    label = stage_name(m, matches) + (f"  ·  {L.t['this_game']}" if current else "")
    d.text((x + 16, y + 10), label, font=_font(24, True), fill=ACCENT if current else DIM)
    yy = y + 44
    for name, sc in ((m.a, sa), (m.b, sb)):
        played = any(g.seq < pick.seq for g in m.games)
        shown = "" if m.mixed else (f"{sc:g}" if played else "–")  # mieszane tempo: bez sumy punktów
        _player_row(img, d, x + 14, yy, w - 28, name, shown,
                    out=(name == loser), winner=(name == win))
        yy += MINI[1] + 14
    return h


def draw_bracket(tournament: str, year: int, matches: list, pick, out: Path) -> Path:
    img = Image.new("RGB", (W, H), BG)
    tournament = re.sub(rf"(^\s*{year}\s*|\s*{year}\s*$)", "", tournament).strip() or tournament
    d = ImageDraw.Draw(img)
    d.line([80, 70, 180, 70], fill=ACCENT, width=6)
    d.text((80, 90), tournament.upper(), font=_fit(d, tournament.upper(), 64, W - 360, True), fill=FG)
    d.text((W - 80 - d.textlength(str(year), font=_font(64, True)), 90), str(year), font=_font(64, True), fill=ACCENT)

    stages = sorted({m.stage for m in matches})
    cols = len(stages)
    box_w = min(620, (W - 160 - (cols - 1) * 80) // cols)
    top, bottom = 220, H - 60
    centers = {}
    for ci, st in enumerate(stages):
        x = 80 + ci * (box_w + 80)
        main = [m for m in matches if m.stage == st and not m.third]
        third = [m for m in matches if m.stage == st and m.third]
        box_h = 2 * MINI[1] + 3 * 14 + 44
        slot = (bottom - top) / max(1, len(main))
        for i, m in enumerate(main):
            y = int(top + slot * i + (slot - box_h) / 2) if not third else int(top + 20 + i * (box_h + 40))
            _box(img, d, x, y, box_w, m, pick, matches)
            centers[(m.a, m.b)] = (x, y + box_h / 2, x + box_w)
            # linie od meczów poprzedniego etapu do tego meczu
            for prev in matches:
                if prev.stage == st - 1 and not prev.third and ({prev.a, prev.b} & {m.a, m.b}):
                    px, py, pr = centers.get((prev.a, prev.b), (None, None, None))
                    if px is not None:
                        mid = (pr + x) / 2
                        d.line([pr, py, mid, py, mid, y + box_h / 2, x, y + box_h / 2], fill=(215, 211, 203), width=4)
        for m in third:
            y = bottom - box_h - 10
            _box(img, d, x, y, box_w, m, pick, matches)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out


def draw_table(tournament: str, year: int, table: list, pick, out: Path) -> Path:
    img = Image.new("RGB", (W, H), BG)
    tournament = re.sub(rf"(^\s*{year}\s*|\s*{year}\s*$)", "", tournament).strip() or tournament
    d = ImageDraw.Draw(img)
    d.line([80, 70, 180, 70], fill=ACCENT, width=6)
    d.text((80, 90), tournament.upper(), font=_fit(d, tournament.upper(), 64, W - 360, True), fill=FG)
    d.text((W - 80 - d.textlength(str(year), font=_font(64, True)), 90), str(year), font=_font(64, True), fill=ACCENT)
    d.text((80, 175), L.t["standings"], font=_font(30, True), fill=DIM)
    rows = table[:8]
    y, row_h = 230, (H - 280) // max(4, len(rows))
    for i, (name, pts) in enumerate(rows):
        hl = name in (pick.white, pick.black)
        d.rounded_rectangle([80, y, W - 80, y + row_h - 12], radius=12, fill=CARD,
                            outline=ACCENT if hl else (60, 58, 55), width=4 if hl else 1)
        d.text((110, y + row_h / 2 - 30), f"{i + 1}.", font=_font(40, True), fill=DIM)
        mini = _mini(name, False).resize((int(MINI[0] * (row_h - 30) / MINI[1]), row_h - 30))
        img.paste(mini, (190, y + 9))
        from news import surname

        last = surname(name).upper()
        d.text((190 + mini.width + 24, y + row_h / 2 - 30), last, font=_font(42, True), fill=FG)
        if hl:
            d.text((190 + mini.width + 34 + d.textlength(last, font=_font(42, True)), y + row_h / 2 - 20),
                   L.t["this_game"], font=_font(24, True), fill=ACCENT)
        s = f"{pts:g} {L.t['pts']}"
        d.text((W - 120 - d.textlength(s, font=_font(42, True)), y + row_h / 2 - 30), s, font=_font(42, True),
               fill=ACCENT if i == 0 else FG)
        y += row_h
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out
