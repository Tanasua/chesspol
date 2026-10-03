"""Ciche dźwięki stawiania figury (własna synteza — bez cudzych licencji), dograne do ścieżki odcinka.

Ruch: miękkie, drewniane "tok" (krótki szum + kilka szybko gasnących tonów). Bicie: odrobinę głośniejsze
i jaśniejsze, z drugim, cichszym odbiciem. Dźwięk startuje w chwili, gdy figura ląduje na polu
(koniec animacji ruchu). Czysty Python (moduły wave/array/math) — bez dodatkowych zależności.
"""
from __future__ import annotations

import array
import math
import os
import random
import wave
from pathlib import Path

RATE = 48000
SFX_GAIN_DB = float(os.environ.get("SFX_GAIN_DB", "-14"))  # względem pełnej skali; lektor ok. -16 LUFS


def _knock(bright: float = 1.0, seed: int = 0, length: float = 0.12) -> list:
    rnd = random.Random(seed)
    n = int(RATE * length)
    tones = [(190.0, 0.022, 0.55), (420.0 * bright, 0.014, 0.35), (1150.0 * bright, 0.006, 0.18)]
    out = []
    for i in range(n):
        t = i / RATE
        s = sum(a * math.exp(-t / tau) * math.sin(2 * math.pi * f * t) for f, tau, a in tones)
        s += (rnd.random() * 2 - 1) * 0.5 * math.exp(-t / 0.0025)  # krótki "klik" uderzenia
        out.append(s)
    peak = max(abs(x) for x in out) or 1.0
    return [x / peak for x in out]


MOVE = _knock(1.0, 1)
CAPTURE = [a + 0.45 * b for a, b in zip(_knock(1.25, 2), [0.0] * int(RATE * 0.035) + _knock(1.3, 3))][: len(MOVE)]


def sfx_track(events: list, plies: list, duration: float, out: Path, land_delay: float) -> Path:
    """events: [Event(time, ply_index)], plies: game.plies; zapis 48 kHz mono WAV długości `duration`."""
    gain = 10 ** (SFX_GAIN_DB / 20) * 32767
    buf = array.array("h", bytes(2 * (int(duration * RATE) + RATE)))
    for e in events:
        ply = plies[e.ply_index - 1]
        clip = CAPTURE if getattr(ply, "is_capture", False) else MOVE
        start = int((e.time + land_delay) * RATE)
        for i, v in enumerate(clip):
            j = start + i
            if j >= len(buf):
                break
            buf[j] = max(-32768, min(32767, buf[j] + int(v * gain)))
    with wave.open(str(out), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(buf.tobytes())
    return out
