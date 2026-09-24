"""Parsowanie scenariusza z markerami ruchów i twarda walidacja względem partii.

Format scenariusza (JSON):
{
  "title": "Partia w operze",
  "segments": [
    {"id": "s01", "text": "Tekst... {{m:1}} ... {{s:2}} ...", "pause_after": 0.6}
  ]
}

Markery:
  {{m:N}}  - półruch N: system WSTAWIA jego polski zapis do lektora
             i animuje ruch na pierwszym słowie tego zapisu.
  {{s:N}}  - półruch N animowany "po cichu" na następnym słowie tekstu.
Półruchy pominięte między markerami są odgrywane automatycznie tuż przed
kolejnym markerem. LLM nigdy nie wypowiada ruchu własnymi słowami —
zapis ruchu pochodzi wyłącznie z PGN, więc nie da się go "przekręcić".
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from pl_notation import spoken

MARKER_RE = re.compile(r"\{\{([ms]):(\d+)\}\}")
# Surowe ruchy w tekście (angielska i polska notacja) — zakazane poza markerami.
RAW_MOVE_RE = re.compile(r"(?<![\w-])(?:[KQRBNHWGS]x?[a-h]?[1-8]?x?[a-h][1-8]|O-O(?:-O)?|[a-h]x[a-h][1-8])(?![\w])")
MAX_AUTO_GAP = 6
# Zapis ruchu jest wstawiany w mianowniku ("goniec na ce cztery") — nie może stać po przyimku
# wymagającym innego przypadku ("po gońcu…"). Taki tekst brzmi niegramatycznie.
PREPOSITIONS = {"po", "przed", "przez", "od", "do", "za", "o", "z", "ze", "na", "w", "we", "nad", "pod",
                "dla", "bez", "wobec", "dzięki", "mimo", "wśród", "podczas", "zamiast"}


class ScriptError(ValueError):
    pass


@dataclass
class Anchor:
    ply_index: int
    token_index: int      # indeks słowa w tekście segmentu, na którym startuje animacja
    spoken: bool


@dataclass
class Segment:
    id: str
    tts_text: str
    tokens: list
    anchors: list = field(default_factory=list)
    pause_after: float = 0.5
    chapter: str = ""


def _tidy(tokens: list, anchors: list) -> tuple[list, list]:
    """Dokleja samotną interpunkcję do poprzedniego słowa i zaczyna zdania wielką literą."""
    out, remap = [], {}
    for i, tok in enumerate(tokens):
        if out and not any(c.isalnum() for c in tok):
            out[-1] += tok
            remap[i] = len(out) - 1
            continue
        if not out or out[-1][-1] in ".!?":
            tok = tok[0].upper() + tok[1:]
        remap[i] = len(out)
        out.append(tok)
    for a in anchors:
        a.token_index = remap.get(a.token_index, len(out) - 1)
    return out, anchors


def load_script(path) -> dict:
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def build_segments(script: dict, game) -> tuple[list, list]:
    """Zwraca (segmenty, ostrzeżenia). Rzuca ScriptError przy błędach krytycznych."""
    n_plies = len(game.plies)
    segments, warnings = [], []
    last_ply = 0

    for raw in script.get("segments", []):
        sid = raw["id"]
        text = raw["text"]

        for m in RAW_MOVE_RE.finditer(MARKER_RE.sub(" ", text)):
            raise ScriptError(f"[{sid}] surowy zapis ruchu '{m.group(0)}' w tekście — użyj markera {{{{m:N}}}}")

        for m in MARKER_RE.finditer(text):
            before = text[:m.start()].rstrip()
            prev_word = before.split()[-1].lower() if before.split() else ""
            if prev_word.strip(",;") in PREPOSITIONS and not before.endswith((",", ";")):
                raise ScriptError(
                    f"[{sid}] marker {m.group(0)} stoi po przyimku '{prev_word}' — zapis ruchu jest w mianowniku, "
                    f"więc zdanie będzie niegramatyczne. Wstaw ruch po dwukropku, np. 'Białe grają: {m.group(0)}.'")
            if m.group(1) == "s" and before and before[-1] not in ".!?:—–" and not MARKER_RE.search(before[-12:]):
                raise ScriptError(
                    f"[{sid}] cichy marker {m.group(0)} stoi w środku zdania — nie jest czytany, więc zdanie się "
                    f"rozpada. Stawiaj {{{{s:N}}}} tylko na początku zdania (po kropce) i nie opieraj na nim treści zdania.")

        tokens, anchors = [], []
        pos = 0
        for m in MARKER_RE.finditer(text):
            tokens.extend(text[pos:m.start()].split())
            kind, n = m.group(1), int(m.group(2))
            if not 1 <= n <= n_plies:
                raise ScriptError(f"[{sid}] marker {m.group(0)} poza zakresem 1..{n_plies}")
            if n <= last_ply:
                raise ScriptError(f"[{sid}] marker {m.group(0)} nie jest rosnący (poprzedni: {last_ply})")
            if n - last_ply - 1 > MAX_AUTO_GAP:
                warnings.append(f"[{sid}] {n - last_ply - 1} półruchów odegranych automatycznie przed {m.group(0)}")
            last_ply = n
            # animacja startuje na następnym słowie (dla 'm' to pierwsze słowo zapisu ruchu)
            anchors.append(Anchor(n, len(tokens), kind == "m"))
            if kind == "m":
                tokens.extend(spoken(game.plies[n - 1]).split())
            pos = m.end()
        tokens.extend(text[pos:].split())

        tokens, anchors = _tidy(tokens, anchors)
        if not tokens:
            raise ScriptError(f"[{sid}] pusty segment")
        for a in anchors:  # cichy marker na samym końcu segmentu -> ostatnie słowo
            a.token_index = min(a.token_index, len(tokens) - 1)
        segments.append(Segment(
            id=sid, tts_text=" ".join(tokens), tokens=tokens, anchors=anchors,
            pause_after=float(raw.get("pause_after", 0.5)),
            chapter=(raw.get("chapter") or "").strip(),
        ))

    if not segments:
        raise ScriptError("Scenariusz nie ma segmentów")
    desc = (script.get("description") or "").strip()
    if desc:
        for m in RAW_MOVE_RE.finditer(desc):
            raise ScriptError(f"[description] surowy zapis ruchu '{m.group(0)}' — w opisie nie podawaj ruchów")
        if len(desc) > 1500:
            raise ScriptError(f"[description] za długi opis ({len(desc)} znaków, maks. 1500)")
    chapters = [s.chapter for s in segments if s.chapter]
    if chapters:
        if not segments[0].chapter:
            raise ScriptError("Pierwszy segment musi mieć rozdział (chapter), np. 'Wstęp'")
        if len(chapters) < 3:
            raise ScriptError(f"Rozdziałów musi być co najmniej 3 (jest {len(chapters)}) albo żadnego")
        for c in chapters:
            if len(c) > 60:
                raise ScriptError(f"Tytuł rozdziału za długi: '{c}' (maks. 60 znaków)")
    if last_ply != n_plies:
        raise ScriptError(f"Scenariusz kończy się na półruchu {last_ply}, a partia ma {n_plies}")
    return segments, warnings
