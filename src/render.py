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

import cairosvg
import chess
import chess.svg
from PIL import Image, ImageDraw, ImageFont, ImageOps

from pl_notation import label, san_pl

W, H = 1920, 1080
SQ = 125
BOARD = 8 * SQ
BOARD_X, BOARD_Y = (W - BOARD) // 2, (H - BOARD) // 2
LEFT_X, LEFT_W = 40, BOARD_X - 80          # treść lewej kolumny
RIGHT_X, RIGHT_W = BOARD_X + BOARD + 40, W - (BOARD_X + BOARD) - 80
PHOTO_W, PHOTO_H = 220, 275

LIGHT, DARK = (238, 216, 181), (181, 136, 99)
HL = (246, 214, 90, 110)
CHECK = (220, 40, 40, 150)
BG, FG, DIM, ACCENT = (12, 12, 12), (240, 236, 228), (135, 130, 122), (246, 214, 90)
CARD = (34, 33, 31)
ANIM_SEC = 0.45
MIN_GAP = ANIM_SEC + 0.05  # animacje nigdy na siebie nie nachodzą

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(FONT_PATHS[1 if bold else 0], size)


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
        img = Image.new("RGBA", (W, H), BG + (255,))
        d = ImageDraw.Draw(img)
        for sq in chess.SQUARES:
            x, y = _sq_xy(sq)
            light = (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1
            d.rectangle([x, y, x + SQ - 1, y + SQ - 1], fill=LIGHT if light else DARK)
        f = _font(20, True)
        for i in range(8):
            d.text((BOARD_X + i * SQ + SQ - 18, BOARD_Y + BOARD - 28), "abcdefgh"[i], font=f,
                   fill=LIGHT if i % 2 == 0 else DARK)
            d.text((BOARD_X + 6, BOARD_Y + i * SQ + 4), str(8 - i), font=f,
                   fill=DARK if i % 2 == 0 else LIGHT)
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
                author = f"fot. {cr.get('author') or 'autor nieznany'}"
                while len(author) > 6 and d.textlength(author + lic, font=f) > PHOTO_W - 10:
                    author = author[:-2] + "…"  # skracamy autora, licencja zostaje w całości
                d.text((5, 5), author + lic, font=f, fill=(225, 225, 225))
                box.alpha_composite(strip, (0, PHOTO_H - 24))
        else:
            d = ImageDraw.Draw(box)
            initials = "".join(w[0] for w in (player["first"] + " " + player["last"]).split()[:3] if w[0].isalpha())
            f = _font(84, True)
            tw = d.textlength(initials.upper(), font=f)
            d.text(((PHOTO_W - tw) / 2, PHOTO_H / 2 - 52), initials.upper(), font=f, fill=DIM)
        return box

    def _name(self, d: ImageDraw.ImageDraw, player: dict, x: int, y: int, piece_white: bool) -> int:
        """Imię (mniejsze) i nazwisko (duże, wersalikami). Zwraca wysokość bloku."""
        r = 9
        d.ellipse([x, y + 8, x + 2 * r, y + 8 + 2 * r],
                  fill=(245, 245, 245) if piece_white else (20, 20, 20), outline=(150, 150, 150), width=2)
        tx = x + 2 * r + 12
        width = LEFT_W - (tx - LEFT_X)
        hgt = 0
        if player["first"]:
            d.text((tx, y + 2), player["first"], font=_fit(d, player["first"], 26, width, False), fill=DIM)
            hgt += 36
        last = player["last"].upper()
        lines = _wrap(d, last, _font(40, True), width, 2)
        if len(lines) > 1:  # długie (np. konsultacja) — mniejszy krój
            lines = _wrap(d, last, _font(30, True), width, 3)
            f, lh = _font(30, True), 36
        else:
            f, lh = _fit(d, last, 40, width, True), 48
        for i, ln in enumerate(lines):
            d.text((tx, y + hgt + i * lh), ln, font=f, fill=FG)
        return hgt + lh * len(lines)

    def left_panel(self, white_to_move: bool) -> Image.Image:
        if white_to_move in self._left:
            return self._left[white_to_move]
        img = Image.new("RGBA", (BOARD_X, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        # czarne u góry (tak jak na szachownicy)
        img.alpha_composite(self._photo(self.black), (LEFT_X, BOARD_Y))
        top_name_y = BOARD_Y + PHOTO_H + 18
        top_h = self._name(d, self.black, LEFT_X, top_name_y, piece_white=False)
        # białe u dołu
        photo_y = BOARD_Y + BOARD - PHOTO_H
        img.alpha_composite(self._photo(self.white), (LEFT_X, photo_y))
        probe = Image.new("RGBA", (BOARD_X, 400))
        bot_h = self._name(ImageDraw.Draw(probe), self.white, LEFT_X, 0, piece_white=True)
        bot_name_y = photo_y - 18 - bot_h
        self._name(d, self.white, LEFT_X, bot_name_y, piece_white=True)
        # pasek przy stronie, która ma ruch
        if white_to_move:
            d.rectangle([LEFT_X - 18, bot_name_y, LEFT_X - 12, photo_y + PHOTO_H], fill=ACCENT)
        else:
            d.rectangle([LEFT_X - 18, BOARD_Y, LEFT_X - 12, top_name_y + top_h], fill=ACCENT)
        # środek: rok + opis
        mid_top, mid_bot = top_name_y + top_h + 20, bot_name_y - 20
        main_cap, _, sub_cap = self.caption.partition(" · ")
        cap_lines = [(ln, FG) for ln in _wrap(d, main_cap, self.f_label, LEFT_W, 3)]
        cap_lines += [(ln, DIM) for ln in _wrap(d, sub_cap, self.f_label, LEFT_W, 1)] if sub_cap else []
        block = 64 + 10 + 34 * len(cap_lines)
        y = mid_top + max(0, (mid_bot - mid_top - block) // 2)
        d.line([LEFT_X, y - 12, LEFT_X + 60, y - 12], fill=ACCENT, width=3)
        d.text((LEFT_X, y), str(self.year), font=_font(56, True), fill=ACCENT)
        for i, (ln, col) in enumerate(cap_lines):
            d.text((LEFT_X, y + 74 + i * 34), ln, font=self.f_label, fill=col)
        self._left[white_to_move] = img
        return img

    def right_panel(self, k: int) -> Image.Image:
        """Panel ruchów po k półruchach."""
        if k in self._right:
            return self._right[k]
        x0 = BOARD_X + BOARD
        img = Image.new("RGBA", (W - x0, H), (0, 0, 0, 0))
        d = ImageDraw.Draw(img)
        lx = RIGHT_X - x0
        d.text((lx, BOARD_Y), "RUCHY", font=self.f_small, fill=DIM)
        cur = label(self.game.plies[k - 1]) if k else "—"
        d.text((lx, BOARD_Y + 30), cur, font=_fit(d, cur, 58, RIGHT_W, True), fill=ACCENT)
        d.line([lx, BOARD_Y + 115, lx + RIGHT_W, BOARD_Y + 115], fill=(60, 58, 55), width=2)

        row_h, top = 40, BOARD_Y + 140
        rows = (BOARD_Y + BOARD - top) // row_h
        plies = self.game.plies
        last_move = plies[-1].move_number
        first_move_no = plies[0].move_number
        cur_move = plies[k - 1].move_number if k else first_move_no
        start = max(first_move_no, cur_move - rows + 1)  # tylko rozegrane ruchy, bieżący na dole
        col_num, col_w, col_b = lx, lx + 70, lx + 70 + (RIGHT_W - 70) // 2
        by_move = {}
        for p in plies:
            by_move.setdefault(p.move_number, {})[p.color] = p
        for i in range(rows):
            mv = start + i
            if mv > min(last_move, cur_move):
                break
            y = top + i * row_h
            d.text((col_num, y + 3), f"{mv}.", font=self.f_num, fill=DIM)
            for color, cx in ((chess.WHITE, col_w), (chess.BLACK, col_b)):
                p = by_move.get(mv, {}).get(color)
                if p is None or p.index > k:
                    continue
                txt = san_pl(p.san)
                if p.index == k:
                    tw = d.textlength(txt, font=self.f_move)
                    d.rounded_rectangle([cx - 8, y - 2, cx + tw + 8, y + row_h - 6], radius=6, fill=(60, 52, 20))
                    d.text((cx, y), txt, font=self.f_move, fill=ACCENT)
                else:
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

    def static(self, k: int) -> Image.Image:
        """Pozycja po k półruchach (0 = start), z podświetleniem ostatniego ruchu."""
        if k not in self._static_cache:
            board = self.boards[k]
            img = self._squares.copy()
            hl, chk = (), None
            if k:
                mv = self.game.plies[k - 1].move
                hl = (mv.from_square, mv.to_square)
                if board.is_check():
                    chk = board.king(board.turn)
            self._overlay(img, hl, chk)
            for sq, piece in board.piece_map().items():
                img.alpha_composite(self.sprites[(piece.piece_type, piece.color)], _sq_xy(sq))
            self._static_cache[k] = self._frame(img, k, board.turn == chess.WHITE).convert("RGB")
        return self._static_cache[k]

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


def schedule(anchor_times: list, n_plies: int) -> list:
    """anchor_times: [(czas, ply_index)] dla półruchów z markerów.
    Półruchy pomiędzy markerami rozkładamy równo tuż przed kolejnym markerem."""
    events, prev_t, prev_ply = [], 0.0, 0
    for t, ply in sorted(anchor_times, key=lambda x: x[1]):
        gap = ply - prev_ply - 1
        if gap > 0:
            room = max(0.0, t - (prev_t + ANIM_SEC))
            step = max(MIN_GAP, min(0.7, room / (gap + 1)))
            for j in range(gap):
                start = t - (gap - j) * step
                floor = events[-1].time + MIN_GAP if events else 0.0
                events.append(Event(max(start, floor, prev_t + MIN_GAP if prev_ply else 0.0), prev_ply + 1 + j))
        floor = events[-1].time + MIN_GAP if events else 0.0
        events.append(Event(max(t, floor), ply))
        prev_t, prev_ply = events[-1].time, ply
    assert [e.ply_index for e in events] == list(range(1, n_plies + 1))
    return events


def render_video(renderer: Renderer, events: list, duration: float, audio_path, out_path, fps: int = 25) -> None:
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
            while ei < len(events) and t >= events[ei].time + ANIM_SEC:
                k = events[ei].ply_index
                ei += 1
            if ei < len(events) and t >= events[ei].time:
                prog = (t - events[ei].time) / ANIM_SEC
                frame = renderer.moving(events[ei].ply_index, prog).tobytes()
            else:
                if last_key != k:
                    last_key, last_bytes = k, renderer.static(k).tobytes()
                frame = last_bytes
            proc.stdin.write(frame)
    finally:
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg zakończył się błędem")
