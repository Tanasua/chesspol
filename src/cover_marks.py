"""Strzałki i znaki "!" / "?" na okładkę — tylko z sensem i z potwierdzeniem silnika (zasada nr 3).

Okładka pokazuje pozycję końcową. Na niej:
  - żółta strzałka: ostatni ruch partii (skąd -> dokąd) — zawsze, bez silnika;
  - czerwona strzałka: groźba zwycięzcy w pozycji końcowej (Stockfish po "ruchu zerowym" przegrywającego) —
    to, przed czym przegrywający się poddał; tylko gdy partia nie skończyła się matem / remisem i nie ma szacha;
  - znak (co trzeci odcinek bez znaku, reszta na zmianę "!" / "?" wg seed, gdy dany znak jest potwierdzony):
      "!"  na ostatnim ruchu zwycięzcy, gdy to pierwszy wybór silnika (albo ≤ BEST_MARGIN gorszy) i pozycja wygrana;
      "?"  na ostatnim ruchu przegrywającego, gdy silnik pokazuje stratę ≥ MISTAKE_DROP (z jego perspektywy);
           wtedy ten ruch dostaje też własną strzałkę (pomarańczową).
Bez Stockfisha: tylko strzałka ostatniego ruchu, bez znaków.
"""
from __future__ import annotations

import hashlib
import os
import shutil
from dataclasses import dataclass, field

import chess
import chess.engine

DEPTH = int(os.environ.get("COVER_ENGINE_DEPTH", "18"))
BEST_MARGIN = 50      # centypiony: "!" także dla ruchu prawie równego najlepszemu (szum głębokości)
MISTAKE_DROP = 150    # centypiony: "?" dopiero przy stracie ≥ 1.5 piona
WINNING = 200         # "!" tylko gdy po ruchu pozycja wygrana (≥ 2 piony albo mat)
MATE = 100_000

YELLOW = "#f5c400cc"
RED = "#e0262bcc"
ORANGE = "#ff8a00cc"
GREEN = "#2fb84acc"


@dataclass
class Marks:
    arrows: list = field(default_factory=list)   # [(from_sq, to_sq, kolor)]
    glyph: str | None = None                     # "!" | "?"
    glyph_square: int | None = None
    notes: list = field(default_factory=list)    # do logu: skąd się wzięły


def _engine_path() -> str | None:
    return os.environ.get("STOCKFISH_PATH") or shutil.which("stockfish") or (
        "/usr/games/stockfish" if os.path.exists("/usr/games/stockfish") else None)


def _cp(info, color: chess.Color) -> int:
    return info["score"].pov(color).score(mate_score=MATE)


def _winner(result: str) -> chess.Color | None:
    return {"1-0": chess.WHITE, "0-1": chess.BLACK}.get(result)


def _variant(seed) -> str | None:
    """Co trzeci odcinek bez znaku, pozostałe na zmianę '!' i '?'."""
    n = seed if isinstance(seed, int) else int(hashlib.sha256(str(seed).encode()).hexdigest(), 16)
    return ("!", "?", None)[n % 3]


def compute(game, seed=0) -> Marks:
    m = Marks()
    plies = game.plies
    last = plies[-1]
    m.arrows.append((last.move.from_square, last.move.to_square, YELLOW))
    path = _engine_path()
    if not path:
        m.notes.append("brak Stockfisha — tylko strzałka ostatniego ruchu")
        return m
    result = game.headers.get("Result", "*")
    winner = _winner(result)
    final = chess.Board(last.fen_after)
    want = _variant(seed)
    with chess.engine.SimpleEngine.popen_uci(path) as eng:
        limit = chess.engine.Limit(depth=DEPTH)

        # groźba zwycięzcy: przegrywający "pasuje", silnik szuka najlepszego ruchu zwycięzcy
        if winner is not None and not final.is_game_over() and final.turn != winner and not final.is_check():
            b = final.copy()
            b.push(chess.Move.null())
            b = chess.Board(b.fen())  # bez historii z ruchem zerowym (UCI jej nie przyjmie)
            info = eng.analyse(b, limit)
            pv = info.get("pv") or []
            # sąsiednie pole: strzałka chowa się pod figurami i tylko zaśmieca — pomijamy
            if pv and _cp(info, winner) >= WINNING and chess.square_distance(pv[0].from_square, pv[0].to_square) > 1:
                m.arrows.append((pv[0].from_square, pv[0].to_square, RED))
                m.notes.append(f"groźba: {b.san(pv[0])} ({info['score'].pov(winner)})")

        def check_bang():
            p = next((p for p in reversed(plies) if winner is not None
                      and chess.Board(p.fen_before).turn == winner), None)
            if not p:
                return None
            before = chess.Board(p.fen_before)
            best = eng.analyse(before, limit)
            after = chess.Board(p.fen_after)
            got = MATE if after.is_checkmate() else -_cp(eng.analyse(after, limit), after.turn)
            top = (best.get("pv") or [None])[0] == p.move
            if got >= WINNING and (top or _cp(best, winner) - got <= BEST_MARGIN):
                return p, f"'!' {p.san}: najlepszy={best['score'].pov(winner)}, po ruchu={got}"
            return None

        def check_mistake():
            loser = (not winner) if winner is not None else None
            p = next((p for p in reversed(plies) if loser is not None
                      and chess.Board(p.fen_before).turn == loser), None)
            if not p:
                return None
            before = chess.Board(p.fen_before)
            b_score = _cp(eng.analyse(before, limit), loser)
            after = chess.Board(p.fen_after)
            a_score = -_cp(eng.analyse(after, limit), after.turn) if not after.is_game_over() else b_score
            if b_score - a_score >= MISTAKE_DROP:
                return p, f"'?' {p.san}: przed={b_score}, po={a_score}"
            return None

        order = {"!": (check_bang, check_mistake), "?": (check_mistake, check_bang), None: ()}[want]
        for fn in order:
            hit = fn()
            if not hit:
                continue
            p, note = hit
            m.glyph = "!" if fn is check_bang else "?"
            m.glyph_square = p.move.to_square
            if p is not last:  # ruch sprzed ostatniego — własna strzałka, żeby było widać, do czego znak
                m.arrows.append((p.move.from_square, p.move.to_square, GREEN if m.glyph == "!" else ORANGE))
            m.notes.append(note)
            break
    return m
