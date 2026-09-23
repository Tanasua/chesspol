"""Render klatek: szachownica z płynnym ruchem figur + panel z listą ruchów.

Klatki idą jako surowe RGB do ffmpeg przez stdin — bez plików pośrednich.
"""
from __future__ import annotations

import io
import subprocess
from dataclasses import dataclass

import cairosvg
import chess
import chess.svg
from PIL import Image, ImageDraw, ImageFont

from pl_notation import label

W, H = 1920, 1080
BOARD_X, BOARD_Y, SQ = 60, 60, 120
PANEL_X = BOARD_X + 8 * SQ + 70
LIGHT, DARK = (232, 220, 196), (156, 123, 91)
HL = (246, 214, 90, 120)
CHECK = (220, 40, 40, 150)
BG, FG, DIM, ACCENT = (24, 22, 20), (240, 236, 228), (140, 132, 120), (246, 214, 90)
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


@dataclass
class Event:
    time: float
    ply_index: int


class Renderer:
    def __init__(self, game, title: str):
        self.game = game
        self.title = title
        self.sprites = _sprites()
        self.boards = [chess.Board(game.start_fen)] + [chess.Board(p.fen_after) for p in game.plies]
        self.f_title, self.f_head = _font(44, True), _font(28)
        self.f_move, self.f_big = _font(30), _font(72, True)
        self._static_cache = {}

    # ---------- warstwy ----------
    def _board_base(self, highlight: tuple = (), check_sq=None) -> Image.Image:
        img = Image.new("RGBA", (W, H), BG + (255,))
        d = ImageDraw.Draw(img)
        for sq in chess.SQUARES:
            x, y = _sq_xy(sq)
            light = (chess.square_file(sq) + chess.square_rank(sq)) % 2 == 1
            d.rectangle([x, y, x + SQ - 1, y + SQ - 1], fill=LIGHT if light else DARK)
        ov = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        od = ImageDraw.Draw(ov)
        for sq in highlight:
            x, y = _sq_xy(sq)
            od.rectangle([x, y, x + SQ - 1, y + SQ - 1], fill=HL)
        if check_sq is not None:
            x, y = _sq_xy(check_sq)
            od.ellipse([x + 6, y + 6, x + SQ - 6, y + SQ - 6], fill=CHECK)
        img.alpha_composite(ov)
        f = _font(20)
        for i in range(8):
            d.text((BOARD_X + i * SQ + SQ - 16, BOARD_Y + 8 * SQ - 26), "abcdefgh"[i], font=f,
                   fill=LIGHT if i % 2 == 0 else DARK)
            d.text((BOARD_X + 4, BOARD_Y + i * SQ + 4), str(8 - i), font=f,
                   fill=DARK if i % 2 == 0 else LIGHT)
        return img

    def _panel(self, img: Image.Image, k: int) -> None:
        d = ImageDraw.Draw(img)
        h = self.game.headers
        d.text((PANEL_X, 70), self.title, font=self.f_title, fill=FG)
        d.text((PANEL_X, 130), f"{h.get('White', '?')} — {h.get('Black', '?')}", font=self.f_head, fill=DIM)
        d.text((PANEL_X, 168), f"{h.get('Site', '')}, {h.get('Date', '').split('.')[0]}", font=self.f_head, fill=DIM)
        if k:
            d.text((PANEL_X, 240), label(self.game.plies[k - 1]), font=self.f_big, fill=ACCENT)
        # ostatnie ruchy w dwóch kolumnach
        y0, rows = 360, 14
        plies = self.game.plies[:k]
        first_move = max(1, (plies[-1].move_number if plies else 1) - rows + 1)
        for p in plies:
            if p.move_number < first_move:
                continue
            row = p.move_number - first_move
            x = PANEL_X + (0 if p.color == chess.WHITE else 300)
            txt = label(p) if p.color == chess.WHITE else label(p).split(" ", 1)[1]
            d.text((x, y0 + row * 44), txt, font=self.f_move, fill=ACCENT if p.index == k else FG)

    def static(self, k: int) -> Image.Image:
        """Pozycja po k półruchach (0 = start), z podświetleniem ostatniego ruchu."""
        if k not in self._static_cache:
            board = self.boards[k]
            hl, chk = (), None
            if k:
                mv = self.game.plies[k - 1].move
                hl = (mv.from_square, mv.to_square)
                if board.is_check():
                    chk = board.king(board.turn)
            img = self._board_base(hl, chk)
            for sq, piece in board.piece_map().items():
                img.alpha_composite(self.sprites[(piece.piece_type, piece.color)], _sq_xy(sq))
            self._panel(img, k)
            self._static_cache[k] = img.convert("RGB")
        return self._static_cache[k]

    def moving(self, k: int, t: float) -> Image.Image:
        """Klatka w trakcie wykonywania półruchu k (t w 0..1)."""
        ply = self.game.plies[k - 1]
        before = self.boards[k - 1]
        mv = ply.move
        e = _ease(t)
        img = self._board_base((mv.from_square,), None)

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
        self._panel(img, k - 1)
        return img.convert("RGB")


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
