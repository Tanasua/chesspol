"""Okładka (miniatura YouTube) 1280x720: pozycja końcowa po lewej, tytuł i gracze po prawej."""
from __future__ import annotations

import io
from pathlib import Path

import cairosvg
import chess
import chess.svg
from PIL import Image, ImageDraw, ImageOps

from countries import badge as flag_badge
from render import ACCENT, BG, DIM, FG, _fit, _font, _wrap

CW, CH = 1280, 720
BOARD_PX = 620
PHOTO = (130, 162)


def _board_png(board: chess.Board, lastmove) -> Image.Image:
    svg = chess.svg.board(board, size=BOARD_PX, coordinates=False, lastmove=lastmove,
                          colors={"square light": "#eed8b5", "square dark": "#b58863",
                                  "square light lastmove": "#f6d65a", "square dark lastmove": "#d9b440"})
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=BOARD_PX, output_height=BOARD_PX)
    return Image.open(io.BytesIO(png)).convert("RGB")


def make_cover(game, title: str, white: dict, black: dict, year: str, out: Path, badge: str = "") -> Path:
    img = Image.new("RGB", (CW, CH), BG)
    last = game.plies[-1]
    img.paste(_board_png(chess.Board(last.fen_after), last.move), (50, (CH - BOARD_PX) // 2))

    d = ImageDraw.Draw(img)
    x, w = 720, CW - 720 - 50
    y = 60
    d.line([x, y, x + 80, y], fill=ACCENT, width=5)
    y += 25
    for size in (64, 56, 50, 44, 40):  # największy krój, przy którym cały tytuł mieści się w 3 wierszach
        f_title = _font(size, True)
        lines = _wrap(d, title.upper(), f_title, w, 3)
        if not lines[-1].endswith("…") and all(d.textlength(ln, font=f_title) <= w for ln in lines):
            break
    lh = f_title.size + 10
    for ln in lines:
        d.text((x, y), ln, font=f_title, fill=FG)
        y += lh
    y += 20
    d.text((x, y), str(year), font=_font(56, True), fill=ACCENT)
    badge = " ".join(x for x in badge.split() if x != str(year))  # rok jest już obok
    if badge:  # turniej / etap, np. "GRAND CHESS TOUR FINALS · FINAŁ"
        bx = x + d.textlength(str(year), font=_font(56, True)) + 24
        fb = _fit(d, badge.upper(), 30, CW - 50 - bx, True)
        lines = _wrap(d, badge.upper(), fb, CW - 50 - bx, 2)
        for i, ln in enumerate(lines):
            d.text((bx, y + 6 + i * (fb.size + 4)), ln, font=fb, fill=FG)
    y += 80

    photos = [p for p in (white, black) if p.get("photo")]
    if len(photos) == 2:  # oba zdjęcia — obok siebie, z nazwiskami pod spodem
        for i, p in enumerate((white, black)):
            px = x + i * (PHOTO[0] + 30)
            ph = ImageOps.fit(Image.open(p["photo"]).convert("RGB"), PHOTO, centering=(0.5, 0.3))
            img.paste(ph, (px, y))
            fl = flag_badge(p.get("country"), 22)
            tx = px
            if fl:  # flaga kraju przy nazwisku, pod portretem
                img.paste(fl, (px, y + PHOTO[1] + 10), fl)
                tx = px + fl.width + 8
            d.text((tx, y + PHOTO[1] + 8), p["last"].upper()[:14], font=_fit(d, p["last"].upper()[:14], 22, PHOTO[0] + 26 - (tx - px), True), fill=FG)
        d.text((x + PHOTO[0] + 4, y + PHOTO[1] // 2 - 16), "vs", font=_font(26, True), fill=DIM)
    else:
        for p in (white, black):
            fl = flag_badge(p.get("country"), 34)
            tx = x + (fl.width + 14 if fl else 0)
            if fl:
                img.paste(fl, (x, y + 6), fl)
            for ln in _wrap(d, p["last"].upper(), _font(40, True), w - (tx - x), 2):
                d.text((tx, y), ln, font=_font(40, True), fill=FG)
                y += 48
            if p is white:
                d.text((x, y), "vs", font=_font(26, True), fill=DIM)
                y += 40
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=90)
    return out
