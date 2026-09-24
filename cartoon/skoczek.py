"""Prototyp mini-kreskówki: maskotka "Skoczek" (koń szachowy) opowiada, jak chodzi skoczek.

Postać rysowana kodem (warstwy: podstawa, szyja, głowa, grzywa, oko, powieka, pysk),
ruch warg sterowany znacznikami czasu słów z Inworld (timestampType WORD),
obok mini-szachownica z ruchem "L" i przeskokiem nad pionami, na dole napisy.

  python cartoon/skoczek.py --out out/skoczek.mp4            # Inworld (INWORLD_API_KEY, INWORLD_VOICE_ID)
  python cartoon/skoczek.py --out out/skoczek.mp4 --dry-run  # cisza + szacowane czasy (test obrazu)
"""
from __future__ import annotations

import argparse
import io
import math
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import cairosvg
import chess
import chess.svg
from PIL import Image, ImageDraw, ImageFilter

SRC = Path(__file__).resolve().parent.parent / "src"
sys.path.insert(0, str(SRC))
from main import build_audio  # noqa: E402
from render import _font  # noqa: E402
from tts_inworld import dry_run, map_tokens_to_times, synthesize  # noqa: E402

W, H, FPS = 1920, 1080, 25
LEAD_IN, TAIL, GAP = 0.8, 1.5, 0.35

# Tekst maskotki — zdania czytane osobno (krótkie pauzy między nimi)
LINES = [
    "Cześć! Jestem Skoczek.",
    "Na szachownicy chodzę inaczej niż wszyscy: dwa pola prosto i jedno w bok, jak litera L.",
    "I jako jedyna figura potrafię przeskakiwać nad innymi!",
    "Dlatego rywale nigdy nie wiedzą, skąd wyskoczę.",
]
# słowo-wyzwalacz -> zdarzenie na mini-szachownicy
TRIGGERS = {"dwa": "lmove", "przeskakiwać": "jump", "wyskoczę": "hop"}

BG_TOP, BG_BOT = (18, 28, 38), (8, 10, 14)
CREAM, OUTLINE, MANE, GOLD = (238, 216, 181), (48, 34, 22), (181, 136, 99), (246, 214, 90)
LIGHT, DARK = (238, 216, 181), (181, 136, 99)
S = 2  # nadpróbkowanie postaci (gładkie krawędzie)

# ---------- postać (współrzędne w płótnie 600x800, pysk w prawo) ----------
HEAD = [(200, 560), (400, 560), (392, 430), (470, 385), (556, 356), (578, 306), (528, 252), (438, 172),
        (384, 142), (362, 62), (330, 150), (262, 200), (222, 300), (202, 452)]
MANE_PTS = [(330, 150), (300, 175), (262, 200), (238, 250), (222, 300), (210, 375), (202, 452)]
PIVOT = (300, 560)


def _rot(pts, ang, pivot=PIVOT):
    c, s = math.cos(ang), math.sin(ang)
    px, py = pivot
    return [(px + (x - px) * c - (y - py) * s, py + (x - px) * s + (y - py) * c) for x, y in pts]


def draw_character(mouth: float, blink: float, tilt: float, look: tuple) -> Image.Image:
    """mouth 0..1, blink 0..1 (1 = zamknięte), tilt w radianach, look = (dx, dy) źrenicy."""
    im = Image.new("RGBA", (600 * S, 800 * S), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    sc = lambda pts: [(x * S, y * S) for x, y in pts]  # noqa: E731
    lw = 8 * S
    # podstawa figury
    d.ellipse(sc([(90, 690), (510, 770)]), fill=CREAM, outline=OUTLINE, width=lw)
    d.polygon(sc([(170, 560), (430, 560), (470, 710), (130, 710)]), fill=CREAM, outline=OUTLINE, width=lw)
    d.ellipse(sc([(160, 540), (440, 590)]), fill=CREAM, outline=OUTLINE, width=lw)
    # głowa z grzywą (obrót wokół szyi)
    head = _rot(HEAD, tilt)
    d.polygon(sc(head), fill=CREAM, outline=OUTLINE, width=lw)
    mane = _rot(MANE_PTS, tilt)
    for (x0, y0), (x1, y1) in zip(mane, mane[1:]):
        mx, my = (x0 + x1) / 2, (y0 + y1) / 2
        nx, ny = -(y1 - y0), (x1 - x0)
        n = math.hypot(nx, ny) or 1
        tip = (mx + nx / n * -34, my + ny / n * -34)
        d.polygon(sc([(x0, y0), tip, (x1, y1)]), fill=MANE, outline=OUTLINE, width=6 * S)
    # oko
    (ex, ey), = _rot([(440, 245)], tilt)
    d.ellipse(sc([(ex - 38, ey - 44), (ex + 38, ey + 44)]), fill=(255, 255, 255), outline=OUTLINE, width=6 * S)
    px, py = ex + 10 + look[0], ey + 4 + look[1]
    d.ellipse(sc([(px - 17, py - 21), (px + 17, py + 21)]), fill=(30, 22, 16))
    d.ellipse(sc([(px - 4, py - 13), (px + 5, py - 4)]), fill=(255, 255, 255))
    if blink > 0:  # powieka opada od góry
        lid = ey - 44 + 88 * blink
        d.chord(sc([(ex - 40, ey - 46), (ex + 40, lid + (46 if blink >= 1 else 10))]), 180, 360, fill=CREAM)
        d.line(sc([(ex - 36, lid), (ex + 36, lid)]), fill=OUTLINE, width=5 * S)
    # brew (lekko unosi się przy mówieniu)
    b = _rot([(402, 190 - 10 * mouth), (470, 198 - 6 * mouth)], tilt)
    d.line(sc(b), fill=OUTLINE, width=9 * S)
    # nozdrze
    (nx_, ny_), = _rot([(548, 318)], tilt)
    d.ellipse(sc([(nx_ - 9, ny_ - 6), (nx_ + 9, ny_ + 6)]), fill=OUTLINE)
    # pysk
    (mx_, my_), = _rot([(515, 368)], tilt)
    h = 6 + 44 * mouth
    d.ellipse(sc([(mx_ - 38, my_ - h / 2), (mx_ + 38, my_ + h / 2)]), fill=(96, 28, 30), outline=OUTLINE, width=5 * S)
    if mouth > 0.35:
        d.ellipse(sc([(mx_ - 18, my_ + h / 2 - 16), (mx_ + 18, my_ + h / 2 - 2)]), fill=(214, 96, 104))
    return im.resize((600, 800), Image.LANCZOS)


# ---------- scena ----------
def background() -> Image.Image:
    bg = Image.new("RGB", (W, H))
    d = ImageDraw.Draw(bg)
    for y in range(H):
        t = y / H
        d.line([(0, y), (W, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(BG_TOP, BG_BOT)))
    # podłoga w perspektywie
    horizon, rows = 760, 7
    for r in range(rows):
        y0 = horizon + (H - horizon) * (r / rows) ** 1.6
        y1 = horizon + (H - horizon) * ((r + 1) / rows) ** 1.6
        for c in range(-24, 25):
            spread0, spread1 = 0.35 + 0.65 * r / rows, 0.35 + 0.65 * (r + 1) / rows
            xa0, xb0 = W / 2 + c * 160 * spread0, W / 2 + (c + 1) * 160 * spread0
            xa1, xb1 = W / 2 + c * 160 * spread1, W / 2 + (c + 1) * 160 * spread1
            col = (58, 46, 34) if (r + c) % 2 else (92, 74, 54)
            d.polygon([(xa0, y0), (xb0, y0), (xb1, y1), (xa1, y1)], fill=col)
    glow = Image.new("L", (W, H), 0)
    ImageDraw.Draw(glow).ellipse([200, 150, 1100, 1000], fill=110)
    glow = glow.filter(ImageFilter.GaussianBlur(160))
    return Image.composite(Image.new("RGB", (W, H), (60, 70, 80)), bg, glow)


def piece_sprite(symbol: str, size: int) -> Image.Image:
    png = cairosvg.svg2png(bytestring=chess.svg.piece(chess.Piece.from_symbol(symbol), size=size).encode(),
                           output_width=size, output_height=size)
    return Image.open(io.BytesIO(png)).convert("RGBA")


class MiniBoard:
    N, SQ, X, Y = 5, 112, 1180, 190

    def __init__(self):
        self.knight = piece_sprite("N", self.SQ)
        self.pawn = piece_sprite("p", self.SQ)

    def xy(self, f, r):
        return self.X + f * self.SQ, self.Y + (self.N - 1 - r) * self.SQ

    def draw(self, img: Image.Image, t: float, ev: dict) -> None:
        d = ImageDraw.Draw(img)
        for f in range(self.N):
            for r in range(self.N):
                x, y = self.xy(f, r)
                d.rectangle([x, y, x + self.SQ - 1, y + self.SQ - 1], fill=LIGHT if (f + r) % 2 else DARK)
        d.rectangle([self.X - 6, self.Y - 6, self.X + self.N * self.SQ + 5, self.Y + self.N * self.SQ + 5],
                    outline=GOLD, width=4)
        pos, scale = (1, 0), 1.0
        # 1) ruch "L": ślad c2 -> c3 -> d3 (tu: (1,1),(1,2),(2,2)), potem skok
        if "lmove" in ev and t >= ev["lmove"]:
            dt = t - ev["lmove"]
            path = [(1, 1), (1, 2), (2, 2)]
            for i, sq in enumerate(path):
                if dt >= 0.45 * i:
                    x, y = self.xy(*sq)
                    a = min(1.0, (dt - 0.45 * i) / 0.3)
                    ov = Image.new("RGBA", (self.SQ, self.SQ), GOLD + (int(150 * a),))
                    img.paste(ov, (x, y), ov)
            k = min(1.0, max(0.0, (dt - 1.5) / 0.6))
            pos = (1 + (2 - 1) * _ease(k), 0 + (2 - 0) * _ease(k))
            scale = 1 + 0.25 * math.sin(math.pi * k)
        # 2) przeskok nad pionami: piony wokół, skok (2,2) -> (3,0)
        if "jump" in ev and t >= ev["jump"] - 0.6:
            for sq in ((2, 1), (3, 1), (3, 2)):
                img.paste(self.pawn, self.xy(*sq), self.pawn)
        if "jump" in ev and t >= ev["jump"]:
            k = min(1.0, (t - ev["jump"]) / 0.9)
            pos = (2 + (3 - 2) * _ease(k), 2 + (0 - 2) * _ease(k))
            scale = 1 + 0.55 * math.sin(math.pi * k)
        # 3) mały skok na koniec: (3,0) -> (4,2)
        if "hop" in ev and t >= ev["hop"]:
            k = min(1.0, (t - ev["hop"]) / 0.7)
            pos = (3 + _ease(k), 0 + 2 * _ease(k))
            scale = 1 + 0.35 * math.sin(math.pi * k)
        spr = self.knight.resize((int(self.SQ * scale),) * 2, Image.LANCZOS)
        x, y = self.xy(*pos)
        off = (self.SQ - spr.width) // 2
        img.paste(spr, (int(x + off), int(y + off - 40 * (scale - 1) * 2)), spr)


def _ease(x: float) -> float:
    x = max(0.0, min(1.0, x))
    return 3 * x * x - 2 * x * x * x


VOWELS = set("aeiouyąęó")


def mouth_at(t: float, words: list) -> float:
    for w in words:
        if w["start"] <= t < w["end"]:
            syl = max(1, sum(ch in VOWELS for ch in w["text"].lower()))
            ph = (t - w["start"]) / max(0.05, w["end"] - w["start"]) * syl
            return 0.15 + 0.85 * abs(math.sin(math.pi * ph))
    return 0.0


def subtitles(img: Image.Image, t: float, words: list, lines: list) -> None:
    cur = next((ln for ln in lines if ln["start"] - 0.2 <= t < ln["end"] + GAP), None)
    if not cur:
        return
    d = ImageDraw.Draw(img)
    f = _font(44, True)
    ws = [w for w in words if w["line"] == cur["i"]]
    chunks, chunk = [], []  # dzielimy zdanie na kawałki mieszczące się w kadrze
    for w in ws:
        test = " ".join(x["text"] for x in chunk + [w])
        if chunk and d.textlength(test, font=f) > W - 360:
            chunks.append(chunk)
            chunk = []
        chunk.append(w)
    chunks.append(chunk)
    show = chunks[0]
    for c in chunks:
        if t >= c[0]["start"] - 0.05:
            show = c
    text = " ".join(w["text"] for w in show)
    total = d.textlength(text, font=f)
    x = (W - total) / 2
    y = H - 110
    d.rounded_rectangle([x - 30, y - 18, x + total + 30, y + 64], radius=18, fill=(0, 0, 0))
    for w in show:
        col = GOLD if w["start"] <= t < w["end"] + 0.05 else (240, 236, 228)
        d.text((x, y), w["text"], font=f, fill=col)
        x += d.textlength(w["text"] + " ", font=f)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--cache", default=".tts_cache")
    args = ap.parse_args()
    voice = os.environ.get("INWORLD_VOICE_ID", "")
    if not args.dry_run and not voice:
        print("Brak INWORLD_VOICE_ID (albo użyj --dry-run)", file=sys.stderr)
        return 2

    cache = Path(args.cache)
    parts, words, lines, events = [("silence", LEAD_IN)], [], [], {}
    cursor = LEAD_IN
    for i, text in enumerate(LINES):
        res = dry_run(text, cache) if args.dry_run else synthesize(text, cache, voice)
        tokens = text.split()
        starts = map_tokens_to_times(tokens, res)
        for j, tok in enumerate(tokens):
            s = cursor + starts[j]
            e = cursor + (starts[j + 1] if j + 1 < len(tokens) else res.duration - 0.1)
            words.append({"text": tok, "start": s, "end": max(s + 0.12, e - 0.04), "line": i})
            key = tok.lower().strip(",.!?:")
            if key in TRIGGERS and TRIGGERS[key] not in events:
                events[TRIGGERS[key]] = s
        lines.append({"i": i, "start": cursor, "end": cursor + res.duration})
        parts += [("file", res.audio_path), ("silence", GAP)]
        cursor += res.duration + GAP
    parts.append(("silence", TAIL))
    duration = cursor + TAIL

    bg = background()
    board = MiniBoard()
    shadow = Image.new("RGBA", (520, 90), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).ellipse([0, 0, 520, 90], fill=(0, 0, 0, 120))
    shadow = shadow.filter(ImageFilter.GaussianBlur(12))
    title_f = _font(30, True)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "voice.wav"
        build_audio(parts, wav, Path(tmp))
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}",
               "-r", str(FPS), "-i", "-", "-i", str(wav), "-c:v", "libx264", "-preset", "veryfast",
               "-crf", "20", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k",
               "-t", f"{duration:.3f}", "-movflags", "+faststart", str(out)]
        proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
        for f in range(int(duration * FPS) + 1):
            t = f / FPS
            mouth = mouth_at(t, words)
            blink_ph = (t + 0.7) % 3.4
            blink = 1.0 if blink_ph < 0.12 else 0.0
            talking = any(w["start"] <= t < w["end"] for w in words)
            tilt = 0.035 * math.sin(t * 2.3) + (0.03 * math.sin(t * 9) if talking else 0)
            jumpk = 0.0
            if "jump" in events and 0 <= t - events["jump"] < 0.9:
                jumpk = math.sin(math.pi * (t - events["jump"]) / 0.9)
            look = (14, 2) if t >= events.get("lmove", 1e9) else (0, 0)
            ch = draw_character(mouth, blink, tilt, look)
            bob = 8 * math.sin(t * 2.3) + 60 * jumpk
            frame = bg.copy()
            frame.paste(shadow, (170, 885), shadow)
            frame.paste(ch, (160, int(180 - bob)), ch)
            board.draw(frame, t, events)
            ImageDraw.Draw(frame).text((1180, 130), "JAK CHODZI SKOCZEK?", font=title_f, fill=GOLD)
            subtitles(frame, t, words, lines)
            proc.stdin.write(frame.tobytes())
        proc.stdin.close()
        if proc.wait() != 0:
            raise RuntimeError("ffmpeg zakończył się błędem")
    print(f"Gotowe: {out} ({duration:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
