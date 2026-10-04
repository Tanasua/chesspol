"""Render klatek 1920x1080: szachownica (kwadrat) na środku, gracze po lewej, ruchy po prawej.

Układ:
  lewa kolumna  — u góry gracz czarnych (zdjęcie + imię i nazwisko), u dołu gracz białych,
                  pośrodku rok i krótki opis partii; pasek przy graczu, który ma ruch
  środek        — szachownica 1000x1000, białe na dole
  prawa kolumna — bieżący ruch dużym krojem + lista ruchów (przewija się z partią)

Klatki idą jako surowe RGB do ffmpeg przez stdin — bez plików pośrednich.
"""
from __future__ import annotations

import io
import subprocess
from dataclasses import dataclass
from pathlib import Path

import cairosvg
import chess
import chess.svg
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from lang import L, credit_author, notation

_N = notation()
label, san_local = _N.label, _N.san_local

W, H = 1920, 1080
SQ = 125
ARROW_GROW = 0.45  # s — czas "wyrastania" strzałki wariantu
ARROW_OLD_ALPHA = 0.38  # krycie starszych strzałek wariantu (najnowsza — pełna)
FADE = 0.5         # s — przejście kolor <-> szarość przy wejściu / wyjściu z wariantu
REWIND_STEP = 0.25  # s — cofanie każdego ruchu wariantu
VAR_HOLD = 1.6     # s — pozycja końcowa wariantu stoi tyle przed cofaniem
BOARD = 8 * SQ
BOARD_X, BOARD_Y = (W - BOARD) // 2, (H - BOARD) // 2
LEFT_X, LEFT_W = 40, BOARD_X - 80          # treść lewej kolumny
RIGHT_X, RIGHT_W = BOARD_X + BOARD + 40, W - (BOARD_X + BOARD) - 80
PHOTO_W, PHOTO_H = 220, 275

# Stylistyka "ciemny lux": grafitowe tło z ciepłym gradientem i winietą, złote akcenty, plansza jak stary pergamin
# w złotej ramie z poświatą, karty z cienką złotą obwódką, nagłówki szeryfowe (Playfair Display, SIL OFL).
LIGHT, DARK = (230, 216, 190), (128, 102, 72)
HL = (214, 168, 64, 150)
CHECK = (200, 40, 36, 150)
BG, FG, DIM, ACCENT = (12, 11, 10), (240, 232, 214), (150, 140, 122), (214, 176, 96)
GOLD_DIM = (140, 112, 60)
CARD = (27, 25, 22)
BG_CENTER, BG_EDGE = (44, 39, 32), (9, 8, 7)
FRAME_PAD = 16  # złota rama wokół planszy
LNUM = ["lnum"]  # Playfair ma domyślnie cyfry nautyczne — w roku i numerze ruchu chcemy równe
ANIM_SEC = 0.45
MIN_GAP = ANIM_SEC + 0.05  # animacje nigdy na siebie nie nachodzą
AUTO_STEP = 1.25  # tempo przewijania pominiętych półruchów (s/ruch); main.py robi na nie miejsce
AUTO_STEP_MAX = 1.5

FONTS = Path(__file__).resolve().parent.parent / "assets" / "fonts"  # Montserrat (SIL OFL, assets/fonts/OFL.txt)
WEIGHTS = {"regular": "Regular", "medium": "Medium", "semibold": "SemiBold", "bold": "Bold",
           "extrabold": "ExtraBold", "black": "Black"}
FALLBACK = ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def _font(size: int, bold: bool = False, weight: str | None = None) -> ImageFont.FreeTypeFont:
    """Montserrat: zwykły tekst — Medium, pogrubiony — Bold; weight= wybiera inną grubość (np. 'black')."""
    name = WEIGHTS.get(weight or ("bold" if bold else "medium"), "Medium")
    if L.font == "Hind":  # kanał hindi: dewanagari (Hind ma wagi Light–Bold; grubsze -> Bold)
        name = name if name in ("Regular", "Medium", "SemiBold", "Bold") else "Bold"
        path = FONTS / "hind" / f"Hind-{name}.ttf"
    else:
        path = FONTS / f"Montserrat-{name}.ttf"
    if path.exists():
        return ImageFont.truetype(str(path), size)
    return ImageFont.truetype(FALLBACK[1 if bold else 0], size)


def _serif(size: int, weight: str = "semibold") -> ImageFont.FreeTypeFont:
    """Nagłówki (rok, bieżący ruch, nazwisko): Playfair Display; kanał hindi — Hind (brak szeryfowego dewanagari)."""
    path = FONTS / "playfair" / f"PlayfairDisplay-{WEIGHTS.get(weight, 'SemiBold')}.ttf"
    if L.font == "Hind" or not path.exists():
        return _font(size, True)
    return ImageFont.truetype(str(path), size)


def _gradient_bg() -> Image.Image:
    """Tło: radialny gradient (ciepły środek -> prawie czarne brzegi) + delikatny ukośny połysk z lewego górnego rogu."""
    mask = Image.radial_gradient("L").resize((W * 2, W * 2)).crop((W - W // 2 - 80, W - H // 2 - 20,
                                                                    W + W // 2 - 80, W + H // 2 - 20))
    mask = mask.point(lambda v: min(255, int((v / 255) ** 0.8 * 300)))  # szybciej ciemnieje ku brzegom
    img = Image.composite(Image.new("RGB", (W, H), BG_EDGE), Image.new("RGB", (W, H), BG_CENTER), mask)
    sheen = Image.linear_gradient("L").rotate(-35, expand=True).resize((W, H)).point(lambda v: max(0, 70 - v) // 3)
    img.paste(Image.new("RGB", (W, H), (90, 78, 58)), (0, 0), sheen)
    grain = Image.effect_noise((W, H), 18).convert("RGB")
    return Image.blend(img, grain, 0.025).convert("RGBA")


def _card(img: Image.Image, box: tuple, active: bool = False, radius: int = 18) -> None:
    """Karta: półprzezroczyste grafitowe tło, cienka złota obwódka; aktywna (strona na ruchu) — jaśniejsza z poświatą."""
    x0, y0, x1, y1 = box
    if active:
        glow = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(glow).rounded_rectangle(box, radius=radius, outline=ACCENT + (230,), width=10)
        img.alpha_composite(glow.filter(ImageFilter.GaussianBlur(12)))
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle(box, radius=radius, fill=CARD + (225,),
                        outline=ACCENT + ((255,) if active else (55,)), width=3 if active else 2)
    img.alpha_composite(layer)


def _ornament(d: ImageDraw.ImageDraw, cx: float, y: float, half: int, crown: bool = True,
              sides: tuple = (-1, 1), gap: int | None = None) -> None:
    """Złoty ozdobnik: linie zanikające ku brzegom i mała korona pośrodku (jak w nagłówku makiety)."""
    gap = gap if gap is not None else (26 if crown else 6)
    for side in sides:
        steps = 24
        for i in range(steps):
            a = int(200 * (1 - i / steps))
            xa = cx + side * (gap + half * i / steps)
            xb = cx + side * (gap + half * (i + 1) / steps)
            d.line([(xa, y), (xb, y)], fill=ACCENT + (a,), width=2)
    if crown:
        w, h = 30, 20
        pts = [(cx - w / 2, y + h / 2), (cx - w / 2, y - h / 2 + 4), (cx - w / 4, y + 1), (cx, y - h / 2),
               (cx + w / 4, y + 1), (cx + w / 2, y - h / 2 + 4), (cx + w / 2, y + h / 2)]
        d.polygon(pts, fill=ACCENT)
        for px in (cx - w / 2, cx, cx + w / 2):
            py = y - h / 2 + (0 if px == cx else 4)
            d.ellipse([px - 3, py - 3, px + 3, py + 3], fill=ACCENT)


def _sprites() -> dict:
    out = {}
    for color in (chess.WHITE, chess.BLACK):
        for pt in range(1, 7):
            p = chess.Piece(pt, color)
            png = cairosvg.svg2png(bytestring=chess.svg.piece(p, size=SQ).encode(),
                                   output_width=SQ, output_height=SQ)
            out[(pt, color)] = Image.open(io.BytesIO(png)).convert("RGBA")
    return out


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 3 * x * x - 2 * x * x * x


def _sq_xy(sq: int) -> tuple:
    f, r = chess.square_file(sq), chess.square_rank(sq)
    return BOARD_X + f * SQ, BOARD_Y + (7 - r) * SQ


def _wrap(draw: ImageDraw.ImageDraw, text: str, font, width: int, max_lines: int) -> list:
    words, lines, cur = text.split(), [], ""
    for w in words:
        test = f"{cur} {w}".strip()
        if draw.textlength(test, font=font) <= width or not cur:
            cur = test
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and draw.textlength(lines[-1] + "…", font=font) > width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += "…"
    return lines


def _fit(draw, text: str, font_size: int, width: int, bold: bool) -> ImageFont.FreeTypeFont:
    size = font_size
    while size > 16 and draw.textlength(text, font=_font(size, bold)) > width:
        size -= 2
    return _font(size, bold)


@dataclass
class Event:
    time: float
    ply_index: int


class Renderer:
    def __init__(self, game, title: str, white: dict | None = None, black: dict | None = None,
                 year: str = "", caption: str = ""):
        self.game = game
        self.title = title
        h = game.headers
        self.white = white or {"name": h.get("White", "?"), "first": "", "last": h.get("White", "?")}
        self.black = black or {"name": h.get("Black", "?"), "first": "", "last": h.get("Black", "?")}
        self.year = year or h.get("Date", "").split(".")[0]
        self.caption = caption or ", ".join(x for x in (h.get("Event", ""), h.get("Site", "")) if x and x != "?")
        self.sprites = _sprites()
        self.boards = [chess.Board(game.start_fen)] + [chess.Board(p.fen_after) for p in game.plies]
        self.f_cur, self.f_move, self.f_num = _font(58, True), _font(28), _font(24)
        self.f_small, self.f_label = _font(20), _font(26)
        self._squares = self._draw_squares()
        self._left = {}
        self._right = {}
        self._static_cache = {}

    # ---------- warstwy ----------
    def _draw_squares(self) -> Image.Image:
        img = _gradient_bg()
        fx0, fy0 = BOARD_X - FRAME_PAD, BOARD_Y - FRAME_PAD
        fx1, fy1 = BOARD_X + BOARD + FRAME_PAD, BOARD_Y + BOARD + FRAME_PAD
        # cień i złota poświata pod ramą
        fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(fx).rounded_rectangle([fx0 + 6, fy0 + 14, fx1 + 6, fy1 + 14], radius=14, fill=(0, 0, 0, 200))
        img.alpha_composite(fx.filter(ImageFilter.GaussianBlur(18)))
        fx = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(fx).rounded_rectangle([fx0, fy0, fx1, fy1], radius=14, outline=ACCENT + (120,), width=10)
        img.alpha_composite(fx.filter(ImageFilter.GaussianBlur(14)))
        d = ImageDraw.Draw(img)
        d.rounded_rectangle([fx0, fy0, fx1, fy1], radius=14, fill=(30, 27, 22), outline=ACCENT, width=2)
        d.rectangle([BOARD_X - 3, BOARD_Y - 3, BOARD_X + BOARD + 2, BOARD_Y + BOARD + 2], outline=GOLD_DIM, width=1)
        # pola jak stary pergamin: jednolite kolory z delikatnym ziarnem (bez gradientu — decyzja właściciela)
        board = Image.new("RGB", (BOARD, BOARD))
        bd = ImageDraw.Draw(board)
        for sq in chess.SQUARES:
            x, y = _sq_xy(sq)
            light = (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1
            bd.rectangle([x - BOARD_X, y - BOARD_Y, x - BOARD_X + SQ - 1, y - BOARD_Y + SQ - 1], fill=LIGHT if light else DARK)
        board = Image.blend(board, Image.effect_noise((BOARD, BOARD), 30).convert("RGB"), 0.05)
        img.paste(board, (BOARD_X, BOARD_Y))
        f = _serif(21, "bold")
        on_light, on_dark = (110, 86, 58), (224, 206, 172)
        for i in range(8):
            d.text((BOARD_X + i * SQ + SQ - 18, BOARD_Y + BOARD - 32), "abcdefgh"[i], font=f,
                   fill=on_dark if i % 2 == 0 else on_light)
            d.text((BOARD_X + 7, BOARD_Y + i * SQ + 2), str(8 - i), font=f,
                   fill=on_light if i % 2 == 0 else on_dark, features=LNUM)
        return img

    def _photo(self, player: dict) -> Image.Image:
        box = Image.new("RGBA", (PHOTO_W, PHOTO_H), CARD + (255,))
        if player.get("photo"):
            src = Image.open(player["photo"]).convert("RGB")
            box = ImageOps.fit(src, (PHOTO_W, PHOTO_H), centering=(0.5, 0.3)).convert("RGBA")
            cr = player.get("credit")
            if cr:
                strip = Image.new("RGBA", (PHOTO_W, 24), (0, 0, 0, 170))
                d = ImageDraw.Draw(strip)
                f = _font(12)
                lic = f" · {cr.get('license', '')}"
                author = f"{L.t['photo_by']} {credit_author(cr.get('author'))}"
                while len(author) > 6 and d.textlength(author + lic, font=f) > PHOTO_W - 10:
                    author = author[:-2] + "…"  # skracamy autora, licencja zostaje w całości
                d.text((5, 5), author + lic, font=f, fill=(225, 225, 225))
                box.alpha_composite(strip, (0, PHOTO_H - 24))
        else:
            d = ImageDraw.Draw(box)
            initials = "".join(w[0] for w in (player["first"] + " " + player["last"]).split()[:3] if w[0].isalpha())
            f = _serif(84, "bold")
            tw = d.textlength(initials.upper(), font=f)
            d.text(((PHOTO_W - tw) / 2, PHOTO_H / 2 - 56), initials.upper(), font=f, fill=GOLD_DIM)
        mask = Image.new("L", (PHOTO_W, PHOTO_H), 0)
        ImageDraw.Draw(mask).rounded_rectangle([0, 0, PHOTO_W - 1, PHOTO_H - 1], radius=14, fill=255)
        box.putalpha(mask)
        ImageDraw.Draw(box).rounded_rectangle([0, 0, PHOTO_W - 1, PHOTO_H - 1], radius=14, outline=ACCENT + (150,), width=2)
        return box

    def _name(self, d: ImageDraw.ImageDraw, player: dict, x: int, y: int, piece_white: bool) -> int:
        """Imię (mniejsze) i nazwisko (duże, wersalikami). Zwraca wysokość bloku."""
        r = 9
        d.ellipse([x, y + 8, x + 2 * r, y + 8 + 2 * r],
                  fill=(245, 240, 228) if piece_white else (16, 15, 13), outline=ACCENT, width=2)
        tx = x + 2 * r + 12
        width = LEFT_W - (tx - LEFT_X)
        hgt = 0
        if player["first"]:
            d.text((tx, y + 2), player["first"], font=_fit(d, player["first"], 26, width, False), fill=DIM)
            hgt += 36
        last = player["last"].upper()
        lines = _wrap(d, last, _serif(40, "bold"), width, 2)
        if len(lines) > 1:  # długie (np. konsultacja) — mniejszy krój
            lines = _wrap(d, last, _serif(30, "bold"), width, 3)
            f, lh = _serif(30, "bold"), 36
        else:
            size = 40
            while size > 18 and d.textlength(last, font=_serif(size, "bold")) > width:
                size -= 2
            f, lh = _serif(size, "bold"), 48
        for i, ln in enumerate(lines):
            d.text((tx, y + hgt + i * lh), ln, font=f, fill=FG)
        hgt += lh * len(lines)
        code = player.get("country")
        if code:  # kraj, który gracz reprezentował: flaga (albo skrót RU/BY/SU/DE) + nazwa w języku kanału
            from countries import badge
            from country_names import country_name

            fl = badge(code, 22)
            name = country_name(code, L.code)
            cx = tx
            if fl:
                d._image.alpha_composite(fl, (int(cx), int(y + hgt + 4)))
                cx += fl.width + 10
            if name:
                d.text((cx, y + hgt + 2), name, font=_fit(d, name, 22, width - (cx - tx), False), fill=DIM)
            if fl or name:
                hgt += 34
        return hgt

    def left_panel(self, white_to_move: bool) -> Image.Image:
        if white_to_move in self._left:
            return self._left[white_to_move]
        img = Image.new("RGBA", (BOARD_X, H), (0, 0, 0, 0))
        probe = Image.new("RGBA", (BOARD_X, 400))
        # karty graczy: czarne u góry (tak jak na szachownicy), białe u dołu; aktywna = strona na ruchu
        top_name_y = BOARD_Y + PHOTO_H + 18
        top_h = self._name(ImageDraw.Draw(probe), self.black, LEFT_X, 0, piece_white=False)
        photo_y = BOARD_Y + BOARD - PHOTO_H
        bot_h = self._name(ImageDraw.Draw(probe), self.white, LEFT_X, 0, piece_white=True)
        bot_name_y = photo_y - 18 - bot_h
        cx0, cx1 = LEFT_X - 22, LEFT_X + LEFT_W + 8
        top_card_bot, bot_card_top = top_name_y + top_h + 10, bot_name_y - 14
        _card(img, (cx0, BOARD_Y - FRAME_PAD, cx1, top_card_bot), active=not white_to_move)
        _card(img, (cx0, bot_card_top, cx1, BOARD_Y + BOARD + FRAME_PAD), active=white_to_move)
        d = ImageDraw.Draw(img)
        img.alpha_composite(self._photo(self.black), (LEFT_X, BOARD_Y))
        self._name(d, self.black, LEFT_X, top_name_y, piece_white=False)
        img.alpha_composite(self._photo(self.white), (LEFT_X, photo_y))
        self._name(d, self.white, LEFT_X, bot_name_y, piece_white=True)
        # środek: ozdobnik, rok (szeryfowy, złoty) + opis
        mid_top, mid_bot = top_card_bot + 14, bot_card_top - 12
        main_cap, _, sub_cap = self.caption.partition(" · ")
        room = max(1, (mid_bot - mid_top - 112) // 34)  # ile wierszy podpisu mieści się między graczami
        cap_lines = [(ln, FG) for ln in _wrap(d, main_cap, self.f_label, LEFT_W, max(1, min(3, room - (1 if sub_cap else 0))))]
        if sub_cap and len(cap_lines) < room:
            cap_lines += [(ln, DIM) for ln in _wrap(d, sub_cap, self.f_label, LEFT_W, 1)]
        block = 26 + 74 + 34 * len(cap_lines)
        y = mid_top + max(0, (mid_bot - mid_top - block) // 2)
        cx = LEFT_X + LEFT_W / 2 - 7
        _ornament(d, cx, y + 8, 120)
        f_year = _serif(60, "bold")
        d.text((cx, y + 26), str(self.year), font=f_year, fill=ACCENT, anchor="ma", features=LNUM)
        for i, (ln, col) in enumerate(cap_lines):
            d.text((cx, y + 26 + 74 + i * 34), ln, font=self.f_label, fill=col, anchor="ma")
        self._left[white_to_move] = img
        return img

    def right_panel(self, k: int) -> Image.Image:
        """Panel ruchów po k półruchach: karta z nagłówkiem, bieżący ruch (szeryfowy, złoty) i lista ruchów w "pigułkach"."""
        if k in self._right:
            return self._right[k]
        x0 = BOARD_X + BOARD
        img = Image.new("RGBA", (W - x0, H), (0, 0, 0, 0))
        lx = RIGHT_X - x0
        _card(img, (lx - 22, BOARD_Y - FRAME_PAD, lx + RIGHT_W + 8, BOARD_Y + BOARD + FRAME_PAD))
        d = ImageDraw.Draw(img)
        mid = lx + RIGHT_W / 2 - 7
        head = L.t["moves_header"].upper()
        f_head = _font(18, True)
        d.text((mid, BOARD_Y + 8), head, font=f_head, fill=ACCENT, anchor="ma")
        hw = d.textlength(head, font=f_head) / 2
        _ornament(d, mid, BOARD_Y + 17, 80, crown=False, gap=int(hw) + 14)
        cur = label(self.game.plies[k - 1]) if k else "—"
        size = 60
        while size > 24 and d.textlength(cur, font=_serif(size, "bold")) > RIGHT_W - 20:
            size -= 2
        d.text((mid, BOARD_Y + 44), cur, font=_serif(size, "bold"), fill=ACCENT, anchor="ma", features=LNUM)
        _ornament(d, mid, BOARD_Y + 132, 150)

        row_h, top = 44, BOARD_Y + 160
        rows = (BOARD_Y + BOARD - top) // row_h
        plies = self.game.plies
        last_move = plies[-1].move_number
        first_move_no = plies[0].move_number
        cur_move = plies[k - 1].move_number if k else first_move_no
        start = max(first_move_no, cur_move - rows + 1)  # tylko rozegrane ruchy, bieżący na dole
        col_num, col_w, col_b = lx, lx + 64, lx + 64 + (RIGHT_W - 64) // 2
        by_move = {}
        for p in plies:
            by_move.setdefault(p.move_number, {})[p.color] = p
        for i in range(rows):
            mv = start + i
            if mv > min(last_move, cur_move):
                break
            y = top + i * row_h
            d.text((col_num, y + 4), f"{mv}.", font=self.f_num, fill=DIM)
            for color, cx in ((chess.WHITE, col_w), (chess.BLACK, col_b)):
                p = by_move.get(mv, {}).get(color)
                if p is None or p.index > k:
                    continue
                txt = san_local(p.san)
                tw = d.textlength(txt, font=self.f_move)
                pill = [cx - 10, y - 2, cx + tw + 10, y + row_h - 8]
                if p.index == k:
                    d.rounded_rectangle(pill, radius=10, fill=(78, 60, 24), outline=ACCENT, width=2)
                    d.text((cx, y), txt, font=self.f_move, fill=(255, 226, 150))
                else:
                    d.rounded_rectangle(pill, radius=10, fill=(42, 38, 33), outline=(74, 66, 54), width=1)
                    d.text((cx, y), txt, font=self.f_move, fill=FG)
        self._right[k] = img
        return img

    def _frame(self, base: Image.Image, k_panel: int, white_to_move: bool) -> Image.Image:
        base.alpha_composite(self.left_panel(white_to_move), (0, 0))
        base.alpha_composite(self.right_panel(k_panel), (BOARD_X + BOARD, 0))
        return base

    def _overlay(self, img: Image.Image, highlight: tuple = (), check_sq=None) -> None:
        if not highlight and check_sq is None:
            return
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        for sq in highlight:
            x, y = _sq_xy(sq)
            od.rectangle([x, y, x + SQ - 1, y + SQ - 1], fill=HL)
        if check_sq is not None:
            x, y = _sq_xy(check_sq)
            od.ellipse([x + 6, y + 6, x + SQ - 6, y + SQ - 6], fill=CHECK)
        img.alpha_composite(ov)

    def _compose(self, k: int, under_pieces: Image.Image | None = None, over_pieces: Image.Image | None = None) -> Image.Image:
        board = self.boards[k]
        img = self._squares.copy()
        hl, chk = (), None
        if k:
            mv = self.game.plies[k - 1].move
            hl = (mv.from_square, mv.to_square)
            if board.is_check():
                chk = board.king(board.turn)
        self._overlay(img, hl, chk)
        if under_pieces is not None:  # strzałki wariantu — pod figurami, żeby ich nie zasłaniały
            img.alpha_composite(under_pieces)
        for sq, piece in board.piece_map().items():
            img.alpha_composite(self.sprites[(piece.piece_type, piece.color)], _sq_xy(sq))
        if over_pieces is not None:
            img.alpha_composite(over_pieces)
        return self._frame(img, k, board.turn == chess.WHITE).convert("RGB")

    def static(self, k: int) -> Image.Image:
        """Pozycja po k półruchach (0 = start), z podświetleniem ostatniego ruchu."""
        if k not in self._static_cache:
            self._static_cache[k] = self._compose(k)
        return self._static_cache[k]

    # ---------- alternatywna rzeczywistość (wariant silnika) ----------
    @staticmethod
    def _arrow_offsets(moves: list) -> list:
        """Przesunięcie w bok dla strzałek na tej samej linii (np. "tam i z powrotem"): biegną równolegle obok siebie."""
        groups = {}
        for i, mv in enumerate(moves):
            groups.setdefault(frozenset((mv.from_square, mv.to_square)), []).append(i)
        out = [0.0] * len(moves)
        for idx in groups.values():
            m = len(idx)
            for pos, i in enumerate(idx):
                out[i] = (pos - (m - 1) / 2) * SQ * 0.26
        return out

    def _arrows_layers(self, arrows: list, t: float) -> tuple:
        """arrows: [(ruch, czas_pojawienia, kolor RGBA, numer, przesunięcie, krycie)] -> (warstwa pod figurami, numery nad)."""
        layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        top = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        d, dt = ImageDraw.Draw(layer), ImageDraw.Draw(top)
        for mv, t0, color, num, off, alpha in arrows:
            if t < t0:
                continue
            prog = min(1.0, (t - t0) / ARROW_GROW)
            (x0, y0), (x1, y1) = _sq_xy(mv.from_square), _sq_xy(mv.to_square)
            x0, y0, x1, y1 = x0 + SQ / 2, y0 + SQ / 2, x1 + SQ / 2, y1 + SQ / 2
            dx, dy = x1 - x0, y1 - y0
            dist = (dx * dx + dy * dy) ** 0.5
            ux, uy = dx / dist, dy / dist
            # stała strona przesunięcia dla pary pól (niezależnie od kierunku), żeby ruchy powrotne szły obok
            a, b = sorted((mv.from_square, mv.to_square))
            cx, cy = _sq_xy(b)[0] - _sq_xy(a)[0], _sq_xy(b)[1] - _sq_xy(a)[1]
            cl = (cx * cx + cy * cy) ** 0.5
            nx, ny = -cy / cl * off, cx / cl * off
            sx, sy = x0 + ux * SQ * 0.2 + nx, y0 + uy * SQ * 0.2 + ny
            tfx, tfy = x1 - ux * SQ * 0.28 + nx, y1 - uy * SQ * 0.28 + ny   # grot na skraju pola docelowego
            e = _ease(prog)
            tip = (sx + (tfx - sx) * e, sy + (tfy - sy) * e)
            head_len, head_w = SQ * 0.30, SQ * 0.17
            seg = ((tip[0] - sx) ** 2 + (tip[1] - sy) ** 2) ** 0.5
            hl = min(head_len, seg)
            base = (tip[0] - ux * hl, tip[1] - uy * hl)
            col = color[:3] + (int(color[3] * alpha),)
            d.line([(sx, sy), base], fill=col, width=int(SQ * 0.10))
            px, py = -uy * head_w * hl / head_len, ux * head_w * hl / head_len
            d.polygon([tip, (base[0] + px, base[1] + py), (base[0] - px, base[1] - py)], fill=col)
            if prog >= 1.0:  # numer kolejności w połowie strzałki
                bx, by, r = (sx + tip[0]) / 2, (sy + tip[1]) / 2, SQ * 0.14
                bcol = color[:3] + (int(255 * max(alpha, 0.5)),)
                dt.ellipse([bx - r, by - r, bx + r, by + r], fill=bcol, outline=(255, 255, 255, bcol[3]), width=2)
                dt.text((bx, by + 1), str(num), font=_font(int(r * 1.3), True), fill=(255, 255, 255, bcol[3]), anchor="mm")
        return layer, top

    def _pieces(self, img: Image.Image, before: chess.Board, mv: chess.Move | None, t: float) -> None:
        """Figury pozycji 'before'; gdy mv — w trakcie ruchu (t 0..1; t malejące = ruch cofany)."""
        if mv is None:
            for sq, piece in before.piece_map().items():
                img.alpha_composite(self.sprites[(piece.piece_type, piece.color)], _sq_xy(sq))
            return
        e = _ease(t)
        movers = {mv.from_square: mv.to_square}
        if before.is_castling(mv):
            rank = chess.square_rank(mv.from_square)
            if chess.square_file(mv.to_square) == 6:
                movers[chess.square(7, rank)] = chess.square(5, rank)
            else:
                movers[chess.square(0, rank)] = chess.square(3, rank)
        captured_sq = None
        if before.is_en_passant(mv):
            captured_sq = chess.square(chess.square_file(mv.to_square), chess.square_rank(mv.from_square))
        elif before.is_capture(mv):
            captured_sq = mv.to_square
        for sq, piece in before.piece_map().items():
            if sq in movers:
                continue
            spr = self.sprites[(piece.piece_type, piece.color)]
            if sq == captured_sq:
                spr = spr.copy()
                spr.putalpha(spr.getchannel("A").point(lambda a: int(a * (1 - _ease((t - 0.5) * 2)))))
            img.alpha_composite(spr, _sq_xy(sq))
        for src, dst in movers.items():
            piece = before.piece_at(src)
            (x0, y0), (x1, y1) = _sq_xy(src), _sq_xy(dst)
            pt = mv.promotion if (src == mv.from_square and mv.promotion and t >= 1) else piece.piece_type
            img.alpha_composite(self.sprites[(pt, piece.color)], (int(x0 + (x1 - x0) * e), int(y0 + (y1 - y0) * e)))

    def alternate(self, var: dict, t: float) -> Image.Image:
        """Klatka "alternatywnej rzeczywistości": wariant silnika na szarej szachownicy, figury naprawdę się ruszają,
        potem szybko wracają (REWIND_STEP s/ruch) i kolor wraca. var — z variation_timeline() + moves/colors."""
        k, moves, steps = var["ply"], var["moves"], var["steps"]
        boards = var.setdefault("_boards", None) or self._alt_boards(var)
        n = len(moves)
        # stan figur
        if t < var["rewind_start"]:
            cur = next((i for i, st in enumerate(steps) if st["move_start"] <= t < st["move_end"]), None)
            if cur is not None:
                before, mv, prog = boards[cur], moves[cur], (t - steps[cur]["move_start"]) / ANIM_SEC
            else:
                done = sum(1 for st in steps if st["move_end"] <= t)
                before, mv, prog = boards[done], None, 0.0
            undone = 0
        else:
            i = min(n, int((t - var["rewind_start"]) / REWIND_STEP))
            if i < n:
                j = n - 1 - i
                before, mv = boards[j], moves[j]
                prog = 1.0 - (t - var["rewind_start"] - i * REWIND_STEP) / REWIND_STEP
            else:
                before, mv, prog = boards[0], None, 0.0
            undone = i
        # strzałki: najnowsza nasycona, starsze półprzezroczyste; cofnięte ruchy tracą strzałkę
        visible = [j for j in range(n - undone) if steps[j]["arrow"] <= t]
        newest = visible[-1] if visible else None
        offs = var.setdefault("_offs", None) or self._arrow_offsets(moves)
        var["_offs"] = offs
        arrows = [(moves[j], steps[j]["arrow"], var["colors"][j], j + 1, offs[j], 1.0 if j == newest else ARROW_OLD_ALPHA)
                  for j in visible]
        under, over = self._arrows_layers(arrows, t)
        # szarość (tylko szachownica i figury; strzałki zostają kolorowe): wejście / wyjście płynne (FADE s)
        if t < var["start"] + FADE:
            g = (t - var["start"]) / FADE
        elif t > var["rewind_end"]:
            g = 1 - (t - var["rewind_end"]) / FADE
        else:
            g = 1.0
        g = max(0.0, min(1.0, g))
        img = self._squares.copy()
        if mv is None and undone == 0 and before is boards[0]:
            gm = self.game.plies[k - 1].move
            self._overlay(img, (gm.from_square, gm.to_square))
        img = _desaturate(img, g)
        img.alpha_composite(under)
        pieces = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        self._pieces(pieces, before, mv, max(0.0, min(1.0, prog)))
        img.alpha_composite(_desaturate(pieces, g))
        img.alpha_composite(over)
        return self._frame(img, k, self.boards[k].turn == chess.WHITE).convert("RGB")

    def _alt_boards(self, var: dict) -> list:
        b = self.boards[var["ply"]].copy()
        out = [b.copy()]
        for mv in var["moves"]:
            b.push(mv)
            out.append(b.copy())
        var["_boards"] = out
        return out

    def moving(self, k: int, t: float) -> Image.Image:
        """Klatka w trakcie wykonywania półruchu k (t w 0..1)."""
        ply = self.game.plies[k - 1]
        before = self.boards[k - 1]
        mv = ply.move
        e = _ease(t)
        img = self._squares.copy()
        self._overlay(img, (mv.from_square,))

        movers = {mv.from_square: mv.to_square}
        if ply.is_castling:
            rank = chess.square_rank(mv.from_square)
            if chess.square_file(mv.to_square) == 6:
                movers[chess.square(7, rank)] = chess.square(5, rank)
            else:
                movers[chess.square(0, rank)] = chess.square(3, rank)
        captured_sq = None
        if ply.is_en_passant:
            captured_sq = chess.square(chess.square_file(mv.to_square), chess.square_rank(mv.from_square))
        elif ply.is_capture:
            captured_sq = mv.to_square

        for sq, piece in before.piece_map().items():
            if sq in movers:
                continue
            spr = self.sprites[(piece.piece_type, piece.color)]
            if sq == captured_sq:
                fade = spr.copy()
                fade.putalpha(fade.getchannel("A").point(lambda a: int(a * (1 - _ease((t - 0.5) * 2)))))
                spr = fade
            img.alpha_composite(spr, _sq_xy(sq))

        for src, dst in movers.items():
            piece = before.piece_at(src)
            (x0, y0), (x1, y1) = _sq_xy(src), _sq_xy(dst)
            pt = mv.promotion if (src == mv.from_square and mv.promotion and t >= 1) else piece.piece_type
            img.alpha_composite(self.sprites[(pt, piece.color)],
                                (int(x0 + (x1 - x0) * e), int(y0 + (y1 - y0) * e)))
        return self._frame(img, k - 1, before.turn == chess.WHITE).convert("RGB")


def _desaturate(img: Image.Image, g: float) -> Image.Image:
    """Szarość obszaru szachownicy w stopniu g (0 = kolor, 1 = odcienie szarości); kanał alfa bez zmian."""
    if g <= 0:
        return img
    box = (BOARD_X, BOARD_Y, BOARD_X + BOARD, BOARD_Y + BOARD)
    region = img.crop(box)
    lum = ImageOps.grayscale(region.convert("RGB"))
    gray = Image.merge("RGBA", (lum, lum, lum, region.getchannel("A")))
    out = img.copy()
    out.paste(Image.blend(region, gray, g), box)
    return out


def variation_timeline(word_times: list) -> dict:
    """Czasy wariantu: strzałka na słowie ruchu, ruch figury tuż po wyrośnięciu strzałki (bez nakładania),
    pauza VAR_HOLD, cofanie REWIND_STEP s/ruch, powrót koloru FADE. 'end' = kiedy partia może ruszyć dalej."""
    steps, prev_end = [], 0.0
    start = word_times[0] - FADE
    for t in word_times:
        ms = max(t + ARROW_GROW, prev_end + 0.05, start + FADE)
        steps.append({"arrow": t, "move_start": ms, "move_end": ms + ANIM_SEC})
        prev_end = ms + ANIM_SEC
    rewind_start = prev_end + VAR_HOLD
    rewind_end = rewind_start + len(word_times) * REWIND_STEP
    return {"start": start, "steps": steps, "rewind_start": rewind_start, "rewind_end": rewind_end,
            "end": rewind_end + FADE}


def schedule(anchor_times: list, n_plies: int, barriers: dict | None = None) -> list:
    """anchor_times: [(czas, ply_index)] dla półruchów z markerów.
    Półruchy pomiędzy markerami rozkładamy równo tuż przed kolejnym markerem
    (do AUTO_STEP_MAX s na ruch; gdy lektor mówi krótko — szybciej, ale nie szybciej niż MIN_GAP).
    barriers: {N: czas} — półruchy po N nie ruszają przed tym czasem (pauza na wariant silnika)."""
    barriers = barriers or {}

    def bar(ply):
        return max((t for n, t in barriers.items() if ply > n), default=0.0)

    events, prev_t, prev_ply = [], 0.0, 0
    for t, ply in sorted(anchor_times, key=lambda x: x[1]):
        gap = ply - prev_ply - 1
        if gap > 0:
            room = max(0.0, t - (prev_t + ANIM_SEC))
            step = max(MIN_GAP, min(AUTO_STEP_MAX, room / (gap + 1)))
            for j in range(gap):
                start = t - (gap - j) * step
                floor = events[-1].time + MIN_GAP if events else 0.0
                events.append(Event(max(start, floor, prev_t + MIN_GAP if prev_ply else 0.0, bar(prev_ply + 1 + j)),
                                    prev_ply + 1 + j))
        floor = events[-1].time + MIN_GAP if events else 0.0
        events.append(Event(max(t, floor, bar(ply)), ply))
        prev_t, prev_ply = events[-1].time, ply
    assert [e.ply_index for e in events] == list(range(1, n_plies + 1))
    return events


def render_video(renderer: Renderer, events: list, duration: float, audio_path, out_path, fps: int = 25,
                 preroll=None, flash=None, variations=None) -> None:
    """preroll: (ścieżka PNG 1920x1080, do_sekundy) — plansza na początku (np. drabinka turnieju).
    flash: (półruch, do_sekundy) — hak: pozycja kluczowa na samym początku, potem zwykły przebieg od startu.
    variations: [{"ply": N, "start": s, "end": s, "arrows": [...]}] — pauza na kluczowym momencie: pozycja po N
    i narastające strzałki wariantu silnika (Renderer.with_arrows)."""
    variations = variations or []
    flash_bytes, flash_until = None, 0.0
    if flash:
        flash_bytes, flash_until = renderer.static(flash[0]).tobytes(), flash[1]
    pre_bytes, pre_until = None, 0.0
    if preroll:
        pre_bytes = Image.open(preroll[0]).convert("RGB").resize((W, H)).tobytes()
        pre_until = preroll[1]
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(fps), "-i", "-",
           "-i", str(audio_path),
           "-c:v", "libx264", "-preset", "veryfast", "-tune", "stillimage", "-crf", "20",
           "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
           "-t", f"{duration:.3f}", "-movflags", "+faststart", str(out_path)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    n_frames = int(duration * fps) + 1
    ei, k = 0, 0
    last_key, last_bytes = None, None
    try:
        for f in range(n_frames):
            t = f / fps
            if flash_bytes and t < flash_until:
                proc.stdin.write(flash_bytes)
                continue
            if pre_bytes and t < pre_until:
                proc.stdin.write(pre_bytes)
                continue
            while ei < len(events) and t >= events[ei].time + ANIM_SEC:
                k = events[ei].ply_index
                ei += 1
            var = next((v for v in variations if v["start"] <= t < v["end"] and v["ply"] == k), None)
            if ei < len(events) and t >= events[ei].time:
                prog = (t - events[ei].time) / ANIM_SEC
                frame = renderer.moving(events[ei].ply_index, prog).tobytes()
            elif var:
                frame = renderer.alternate(var, t).tobytes()
            else:
                if last_key != k:
                    last_key, last_bytes = k, renderer.static(k).tobytes()
                frame = last_bytes
            proc.stdin.write(frame)
    finally:
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg zakończył się błędem")
