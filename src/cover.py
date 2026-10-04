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
PHOTO = (176, 210)
GAP = 44
GLYPH_COLORS = {"!": (38, 166, 65), "?": (214, 40, 40)}  # odstęp między portretami (tu napis 'vs')


def _board_png(board: chess.Board, lastmove, arrows=()) -> Image.Image:
    arrows = [chess.svg.Arrow(a, b, color=c) for a, b, c in arrows]
    svg = chess.svg.board(board, size=BOARD_PX, coordinates=False, lastmove=lastmove, arrows=arrows,
                          colors={"square light": "#eed8b5", "square dark": "#b58863",
                                  "square light lastmove": "#f6d65a", "square dark lastmove": "#d9b440"})
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=BOARD_PX, output_height=BOARD_PX)
    return Image.open(io.BytesIO(png)).convert("RGB")


def _glyph(img: Image.Image, origin: tuple, square: int, glyph: str) -> None:
    """Znak '!' (zielony) / '?' (czerwony) w kółku w prawym górnym rogu pola — jak w serwisach szachowych."""
    sq = BOARD_PX / 8
    cx = origin[0] + (chess.square_file(square) + 1) * sq - sq * 0.12
    cy = origin[1] + (7 - chess.square_rank(square)) * sq + sq * 0.12
    r = int(sq * 0.30)
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GLYPH_COLORS[glyph], outline=(255, 255, 255), width=3)
    f = _font(int(r * 1.5), True, weight="black")
    d.text((cx, cy + 1), glyph, font=f, fill=(255, 255, 255), anchor="mm")


def make_cover(game, title: str, white: dict, black: dict, year: str, out: Path, badge: str = "",
               marks=None) -> Path:
    """marks: cover_marks.Marks (strzałki + znak '!'/'?'); None = tylko podświetlenie ostatniego ruchu."""
    img = Image.new("RGB", (CW, CH), BG)
    last = game.plies[-1]
    origin = (50, (CH - BOARD_PX) // 2)
    img.paste(_board_png(chess.Board(last.fen_after), last.move, marks.arrows if marks else ()), origin)
    if marks and marks.glyph:
        _glyph(img, origin, marks.glyph_square, marks.glyph)

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
            px = x + i * (PHOTO[0] + GAP)
            ph = ImageOps.fit(Image.open(p["photo"]).convert("RGB"), PHOTO, centering=(0.5, 0.3))
            img.paste(ph, (px, y))
            fl = flag_badge(p.get("country"), 24)
            if fl:  # flaga w dolnym lewym rogu portretu — nazwisko ma pod zdjęciem całą szerokość kolumny
                img.paste(fl, (px + 6, y + PHOTO[1] - fl.height - 6), fl)
            last = p["last"].upper()
            col_w = PHOTO[0] + GAP - 10  # kolumna = zdjęcie + część odstępu do następnej
            size = 26
            while size > 10 and d.textlength(last, font=_font(size, True)) > col_w:
                size -= 1
            d.text((px, y + PHOTO[1] + 8), last, font=_font(size, True), fill=FG)
        fvs = _font(26, True)
        d.text((x + PHOTO[0] + (GAP - d.textlength("vs", font=fvs)) / 2, y + PHOTO[1] // 2 - 16), "vs", font=fvs, fill=DIM)
    else:
        for p in (white, black):
            fl = flag_badge(p.get("country"), 34)
            tx = x + (fl.width + 14 if fl else 0)
            if fl:
                img.paste(fl, (x, y + 6), fl)
            for size in (40, 34, 30, 26):  # całe nazwisko w 2 wierszach, bez "…"
                lines = _wrap(d, p["last"].upper(), _font(size, True), w - (tx - x), 2)
                if not lines[-1].endswith("…"):
                    break
            for ln in lines:
                d.text((tx, y), ln, font=_font(size, True), fill=FG)
                y += size + 8
            if p is white:
                d.text((x, y), "vs", font=_font(26, True), fill=DIM)
                y += 40
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=90)
    return out
