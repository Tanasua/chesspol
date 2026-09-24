"""Okładka (miniatura YouTube) 1280x720: pozycja końcowa po lewej, tytuł i gracze po prawej."""
from __future__ import annotations

import io
from pathlib import Path

import cairosvg
import chess
import chess.svg
from PIL import Image, ImageDraw, ImageOps

from render import ACCENT, BG, DIM, FG, _font, _wrap

CW, CH = 1280, 720
BOARD_PX = 620
PHOTO = (130, 162)


def _board_png(board: chess.Board, lastmove) -> Image.Image:
    svg = chess.svg.board(board, size=BOARD_PX, coordinates=False, lastmove=lastmove,
                          colors={"square light": "#eed8b5", "square dark": "#b58863",
                                  "square light lastmove": "#f6d65a", "square dark lastmove": "#d9b440"})
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=BOARD_PX, output_height=BOARD_PX)
    return Image.open(io.BytesIO(png)).convert("RGB")


def make_cover(game, title: str, white: dict, black: dict, year: str, out: Path) -> Path:
    img = Image.new("RGB", (CW, CH), BG)
    last = game.plies[-1]
    img.paste(_board_png(chess.Board(last.fen_after), last.move), (50, (CH - BOARD_PX) // 2))

    d = ImageDraw.Draw(img)
    x, w = 720, CW - 720 - 50
    y = 60
    d.line([x, y, x + 80, y], fill=ACCENT, width=5)
    y += 25
    f_title = _font(64, True)
    lines = _wrap(d, title.upper(), f_title, w, 3)
    if len(lines) == 3:
        f_title = _font(54, True)
        lines = _wrap(d, title.upper(), f_title, w, 3)
    lh = f_title.size + 10
    for ln in lines:
        d.text((x, y), ln, font=f_title, fill=FG)
        y += lh
    y += 20
    d.text((x, y), str(year), font=_font(56, True), fill=ACCENT)
    y += 80

    photos = [p for p in (white, black) if p.get("photo")]
    if len(photos) == 2:  # oba zdjęcia — obok siebie, z nazwiskami pod spodem
        for i, p in enumerate((white, black)):
            px = x + i * (PHOTO[0] + 30)
            ph = ImageOps.fit(Image.open(p["photo"]).convert("RGB"), PHOTO, centering=(0.5, 0.3))
            img.paste(ph, (px, y))
            d.text((px, y + PHOTO[1] + 8), p["last"].upper()[:14], font=_font(22, True), fill=FG)
        d.text((x + PHOTO[0] + 4, y + PHOTO[1] // 2 - 16), "vs", font=_font(26, True), fill=DIM)
    else:
        for p in (white, black):
            for ln in _wrap(d, p["last"].upper(), _font(40, True), w, 2):
                d.text((x, y), ln, font=_font(40, True), fill=FG)
                y += 48
            if p is white:
                d.text((x, y), "vs", font=_font(26, True), fill=DIM)
                y += 40
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "JPEG", quality=90)
    return out
