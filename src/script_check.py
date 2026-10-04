"""Parsowanie scenariusza z markerami ruchów i twarda walidacja względem partii.

Format scenariusza (JSON):
{
  "title": "Partia w operze",
  "segments": [
    {"id": "s01", "text": "Tekst... {{m:1}} ... {{s:2}} ...", "pause_after": 0.6}
  ]
}

Markery:
  {{m:N}}  - półruch N: system WSTAWIA jego zapis słowny (w języku kanału) do lektora
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

from lang import notation

_N = notation()
spoken = _N.spoken
PREPOSITIONS = _N.PREPOSITIONS

MARKER_RE = re.compile(r"\{\{([ms]):(\d+)\}\}")
# Surowe ruchy w tekście (notacja angielska, polska i niemiecka) — zakazane poza markerami.
RAW_MOVE_RE = re.compile(r"(?<![\w-])(?:[KQRBNHWGSDTL]x?[a-h]?[1-8]?x?[a-h][1-8]|O-O(?:-O)?|[a-h]x[a-h][1-8])(?![\w])")
MAX_AUTO_GAP = 6


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


HOOK_MIN, HOOK_MAX = 40, 300


def build_hook(script: dict, game) -> tuple[Segment | None, int | None]:
    """Hak na sam początek (przed powitaniem): {"text": "...", "ply": N}. Tekst bez ruchów, markerów i cyfr;
    ply = pozycja kluczowa pokazywana na szachownicy, gdy lektor czyta hak. Stare scenariusze bez haka -> (None, None)."""
    hook = script.get("hook")
    if not hook:
        return None, None
    text = " ".join(str(hook.get("text") or "").split())
    ply = hook.get("ply")
    if not HOOK_MIN <= len(text) <= HOOK_MAX:
        raise ScriptError(f"[hook] tekst musi mieć {HOOK_MIN}–{HOOK_MAX} znaków (ma {len(text)})")
    if MARKER_RE.search(text):
        raise ScriptError("[hook] bez markerów ruchów — hak niczego nie odgrywa, pozycję wskazuje pole \"ply\"")
    for m in RAW_MOVE_RE.finditer(text):
        raise ScriptError(f"[hook] surowy zapis ruchu '{m.group(0)}' — w haku nie podawaj ruchów")
    if any(c.isdigit() for c in text):
        raise ScriptError("[hook] liczby słownie (lektor), bez cyfr")
    if not isinstance(ply, int) or not 1 <= ply <= len(game.plies):
        raise ScriptError(f"[hook] pole \"ply\" musi być numerem półruchu 1..{len(game.plies)}")
    return Segment(id="hook", tts_text=text, tokens=text.split(), pause_after=0.8), ply


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
    title = (script.get("title") or "").strip()
    if len(title) > 70:
        raise ScriptError(f"[title] za długi tytuł ({len(title)} znaków, maks. 70) — bez nazwisk i roku")
    kicker = (script.get("kicker") or "").strip()
    if kicker:  # krzykliwy początek tytułu YouTube, np. "NIESAMOWITE!" / "WAS FÜR EINE PARTIE!"
        words = kicker.split()
        if len(words) > 4 or len(kicker) > 30:
            raise ScriptError(f"[kicker] za długi: '{kicker}' (maks. 4 słowa, 30 znaków)")
        if kicker != kicker.upper() or not any(c.isalpha() for c in kicker):
            raise ScriptError(f"[kicker] musi być WERSALIKAMI: '{kicker}'")
        if kicker[-1] not in "!?":
            raise ScriptError(f"[kicker] musi kończyć się wykrzyknikiem lub pytajnikiem: '{kicker}'")
        if RAW_MOVE_RE.search(kicker) or any(c.isdigit() for c in kicker):
            raise ScriptError(f"[kicker] bez ruchów i liczb: '{kicker}'")
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
    build_hook(script, game)  # walidacja haka (jeśli jest)
    return segments, warnings
