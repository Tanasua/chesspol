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
  {{p}}    - pauza "pomyśl sam" (THINK s ciszy, szachownica stoi) tuż przed ważnym ruchem {{m:N}}; maks. 3.
  {{v:N}}  - wariant silnika z pozycji po kluczowym półruchu N (script["key_moments"], src/key_moments.py):
             system czyta jego ruchy i rysuje je narastającymi strzałkami; partia stoi w miejscu.
Półruchy pominięte między markerami są odgrywane automatycznie tuż przed
kolejnym markerem. LLM nigdy nie wypowiada ruchu własnymi słowami —
zapis ruchu pochodzi wyłącznie z PGN, więc nie da się go "przekręcić".
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

import chess

from key_moments import line_plies
from lang import notation

_N = notation()
spoken = _N.spoken
PREPOSITIONS = _N.PREPOSITIONS

MARKER_RE = re.compile(r"\{\{([msv]):(\d+)\}\}")
# Surowe ruchy w tekście (notacja angielska, polska i niemiecka) — zakazane poza markerami.
RAW_MOVE_RE = re.compile(r"(?<![\w-])(?:[KQRBNHWGSDTL]x?[a-h]?[1-8]?x?[a-h][1-8]|O-O(?:-O)?|[a-h]x[a-h][1-8])(?![\w])")
MAX_AUTO_GAP = 6
THINK_RE = re.compile(r"\{\{p\}\}")   # pauza "pomyśl sam" przed ważnym ruchem
THINK_TOKEN = "\u23f8"                  # znacznik roboczy w tokenach (usuwany przed TTS)
MAX_THINK = 3


class ScriptError(ValueError):
    pass


@dataclass
class Anchor:
    ply_index: int
    token_index: int      # indeks słowa w tekście segmentu, na którym startuje animacja
    spoken: bool


@dataclass
class VarMark:
    """Ruch wariantu silnika (marker {{v:N}}): strzałka pojawia się na słowie token_index."""
    ply_index: int        # kluczowy półruch N — wariant z pozycji PO nim
    line_index: int       # który ruch wariantu (0..)
    token_index: int


@dataclass
class Segment:
    id: str
    tts_text: str
    tokens: list
    anchors: list = field(default_factory=list)
    pause_after: float = 0.5
    chapter: str = ""
    variations: list = field(default_factory=list)   # [VarMark]
    pauses: list = field(default_factory=list)       # indeksy słów, PRZED którymi lektor milknie na THINK s


def _tidy(tokens: list, anchors: list) -> tuple[list, list]:
    """Dokleja samotną interpunkcję do poprzedniego słowa i zaczyna zdania wielką literą."""
    out, remap = [], {}
    for i, tok in enumerate(tokens):
        if out and not any(c.isalnum() for c in tok):
            out[-1] += tok
            remap[i] = len(out) - 1
            continue
        if not out or out[-1][-1] in ".!?।":
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
    moments = {km["ply"]: km for km in script.get("key_moments") or []}
    used_v = set()

    n_think = 0
    for raw in script.get("segments", []):
        sid = raw["id"]
        text = raw["text"]
        for m in THINK_RE.finditer(text):  # po {{p}} w tym segmencie musi przyjść ruch czytany {{m:N}}
            nxt = MARKER_RE.search(text, m.end())
            if not nxt or nxt.group(1) != "m":
                raise ScriptError(f"[{sid}] {{{{p}}}} musi stać przed markerem {{{{m:N}}}} ważnego ruchu w tym samym segmencie")
            n_think += 1
        if n_think > MAX_THINK:
            raise ScriptError(f"Za dużo pauz {{{{p}}}} (maks. {MAX_THINK} na odcinek)")
        text = THINK_RE.sub(f" {THINK_TOKEN} ", text)

        for m in RAW_MOVE_RE.finditer(MARKER_RE.sub(" ", text)):
            raise ScriptError(f"[{sid}] surowy zapis ruchu '{m.group(0)}' w tekście — użyj markera {{{{m:N}}}}")

        for m in MARKER_RE.finditer(text):
            before = text[:m.start()].rstrip()
            prev_word = before.split()[-1].lower() if before.split() else ""
            if prev_word.strip(",;") in PREPOSITIONS and not before.endswith((",", ";")):
                raise ScriptError(
                    f"[{sid}] marker {m.group(0)} stoi po przyimku '{prev_word}' — zapis ruchu jest w mianowniku, "
                    f"więc zdanie będzie niegramatyczne. Wstaw ruch po dwukropku, np. 'Białe grają: {m.group(0)}.'")
            if m.group(1) == "s" and before and before[-1] not in ".!?:—–।" and not MARKER_RE.search(before[-12:]):
                raise ScriptError(
                    f"[{sid}] cichy marker {m.group(0)} stoi w środku zdania — nie jest czytany, więc zdanie się "
                    f"rozpada. Stawiaj {{{{s:N}}}} tylko na początku zdania (po kropce) i nie opieraj na nim treści zdania.")

        tokens, anchors, vmarks = [], [], []
        pos = 0
        for m in MARKER_RE.finditer(text):
            tokens.extend(text[pos:m.start()].split())
            kind, n = m.group(1), int(m.group(2))
            if kind == "v":  # wariant silnika z pozycji po kluczowym półruchu N — czyta i rysuje system
                if n not in moments:
                    raise ScriptError(f"[{sid}] {m.group(0)}: półruch {n} nie jest kluczowym momentem "
                                      f"(dozwolone: {sorted(moments) or 'brak'})")
                if n in used_v:
                    raise ScriptError(f"[{sid}] {m.group(0)} użyty drugi raz")
                if last_ply != n:
                    raise ScriptError(f"[{sid}] {m.group(0)} musi stać zaraz po markerze półruchu {n} "
                                      f"(przed kolejnymi ruchami partii; teraz ostatni: {last_ply})")
                used_v.add(n)
                lp = line_plies(game.plies[n - 1].fen_after, [chess.Move.from_uci(u) for u in moments[n]["line"]])
                for j, vp in enumerate(lp):
                    vmarks.append(VarMark(n, j, len(tokens)))
                    words = spoken(vp).split()
                    if j < len(lp) - 1 and not words[-1].endswith((",", ".", "!", "?")):
                        words[-1] += ","
                    tokens.extend(words)
                pos = m.end()
                continue
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

        pauses = []
        if THINK_TOKEN in tokens:  # usuwamy znaczniki pauz, przesuwając indeksy kotwic i strzałek
            keep, remap = [], {}
            for i, tok in enumerate(tokens):
                if tok == THINK_TOKEN:
                    pauses.append(len(keep))
                    continue
                remap[i] = len(keep)
                keep.append(tok)
            for a in anchors + vmarks:
                a.token_index = remap.get(a.token_index, len(keep) - 1)
            tokens = keep
        pause_marks = [Anchor(0, i, False) for i in pauses]
        tokens, _ = _tidy(tokens, anchors + vmarks + pause_marks)
        pauses = [pm.token_index for pm in pause_marks]
        if not tokens:
            raise ScriptError(f"[{sid}] pusty segment")
        for a in anchors:  # cichy marker na samym końcu segmentu -> ostatnie słowo
            a.token_index = min(a.token_index, len(tokens) - 1)
        segments.append(Segment(
            id=sid, tts_text=" ".join(tokens), tokens=tokens, anchors=anchors,
            pause_after=float(raw.get("pause_after", 0.5)),
            chapter=(raw.get("chapter") or "").strip(), variations=vmarks, pauses=pauses,
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
    yt_hook, yt_detail = (script.get("yt_hook") or "").strip(), (script.get("yt_detail") or "").strip()
    if yt_hook:  # tytuł YouTube — osobny od okładki (kicker + title)
        if len(yt_hook) > 45 or len(yt_hook.split()) < 2:
            raise ScriptError(f"[yt_hook] 2–7 słów, maks. 45 znaków: '{yt_hook}'")
        if RAW_MOVE_RE.search(yt_hook):
            raise ScriptError(f"[yt_hook] bez zapisu ruchów: '{yt_hook}'")
        cover_words = {w for w in re.findall(r"\w+", f"{kicker} {title}".lower()) if len(w) > 3}
        hook_words = {w for w in re.findall(r"\w+", yt_hook.lower()) if len(w) > 3}
        if hook_words and len(hook_words & cover_words) / len(hook_words) > 0.5:
            raise ScriptError(f"[yt_hook] ma być INNĄ frazą niż okładka (kicker + title) — "
                              f"powtarza: {sorted(hook_words & cover_words)}")
    if yt_detail:
        if len(yt_detail) > 60:
            raise ScriptError(f"[yt_detail] maks. 60 znaków: '{yt_detail}'")
        if RAW_MOVE_RE.search(yt_detail):
            raise ScriptError(f"[yt_detail] bez zapisu ruchów: '{yt_detail}'")
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
    missing = sorted(set(moments) - used_v)
    if missing:
        raise ScriptError("Brak markerów wariantu silnika dla kluczowych momentów: "
                          + ", ".join(f"{{{{v:{n}}}}}" for n in missing)
                          + " — wstaw każdy raz, zaraz po markerze tego półruchu")
    build_hook(script, game)  # walidacja haka (jeśli jest)
    return segments, warnings
