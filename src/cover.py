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
GAP = 44  # odstęp między portretami (tu napis 'vs')
GLYPH_COLORS = {"!": (38, 166, 65), "?": (214, 40, 40)}


SQ_COLORS = {"square light": "#eed8b5", "square dark": "#b58863",
             "square light lastmove": "#f6d65a", "square dark lastmove": "#d9b440"}
CLEAR = {k: "#00000000" for k in SQ_COLORS}
SS = 4  # nadpróbkowanie strzałek (gładkie krawędzie)


def _svg_png(svg: str) -> Image.Image:
    png = cairosvg.svg2png(bytestring=svg.encode(), output_width=BOARD_PX, output_height=BOARD_PX)
    return Image.open(io.BytesIO(png)).convert("RGBA")


def _rgba(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4)) + ((int(h[6:8], 16),) if len(h) == 8 else (255,))


def _arrows_layer(arrows) -> Image.Image:
    """Cienkie strzałki POD figurami: grot kończy się na skraju pola docelowego, więc figura zostaje odkryta."""
    sq = BOARD_PX / 8 * SS
    layer = Image.new("RGBA", (BOARD_PX * SS, BOARD_PX * SS), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)

    def center(s):
        return ((chess.square_file(s) + 0.5) * sq, (7.5 - chess.square_rank(s)) * sq)

    for a, b, color in arrows:
        (x0, y0), (x1, y1) = center(a), center(b)
        dx, dy = x1 - x0, y1 - y0
        dist = (dx * dx + dy * dy) ** 0.5
        ux, uy = dx / dist, dy / dist
        tip = (x1 - ux * sq * 0.30, y1 - uy * sq * 0.30)          # grot przy krawędzi pola
        head_len, head_w, width = sq * 0.30, sq * 0.15, sq * 0.075
        base = (tip[0] - ux * head_len, tip[1] - uy * head_len)
        start = (x0 + ux * sq * 0.18, y0 + uy * sq * 0.18)
        col = _rgba(color)
        d.line([start, base], fill=col, width=int(width))
        px, py = -uy * head_w, ux * head_w
        d.polygon([tip, (base[0] + px, base[1] + py), (base[0] - px, base[1] - py)], fill=col)
    return layer.resize((BOARD_PX, BOARD_PX), Image.LANCZOS)


def _board_png(board: chess.Board, lastmove, arrows=()) -> Image.Image:
    """Warstwy: pola -> strzałki -> figury (figury zawsze w pełni widoczne, także dla modelu OpenAI)."""
    squares = _svg_png(chess.svg.board(chess.Board(None), size=BOARD_PX, coordinates=False,
                                       lastmove=lastmove, colors=SQ_COLORS))
    pieces = _svg_png(chess.svg.board(board, size=BOARD_PX, coordinates=False, colors=CLEAR))
    if arrows:
        squares = Image.alpha_composite(squares, _arrows_layer(arrows))
    return Image.alpha_composite(squares, pieces).convert("RGB")


def _glyph(img: Image.Image, origin: tuple, square: int, glyph: str) -> None:
    """Mały znak '!' (zielony) / '?' (czerwony) w kółku na prawym górnym rogu pola — poza obrysem figury."""
    sq = BOARD_PX / 8
    cx = origin[0] + (chess.square_file(square) + 1) * sq - sq * 0.08
    cy = origin[1] + (7 - chess.square_rank(square)) * sq + sq * 0.08
    r = int(sq * 0.19)
    d = ImageDraw.Draw(img)
    d.ellipse([cx - r, cy - r, cx + r, cy + r], fill=GLYPH_COLORS[glyph], outline=(255, 255, 255), width=2)
    f = _font(int(r * 1.45), True, weight="black")
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
