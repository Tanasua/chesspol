"""Kluczowe momenty partii (Stockfish, zasada nr 3) i warianty silnika do pokazania strzałkami.

Rodzaje:
  - "sacrifice": ruch oddaje materiał (≥ 3 punkty: lekka figura i więcej), strata NIE wraca przez kolejne ruchy
    (sprawdzamy po 1, 3 i 5 półruchach), a ocena silnika z perspektywy grającego nie spada (≤ 0.5 piona);
  - "turn": największa zmiana oceny (≥ 2 piony) w pozycji, która nie była jeszcze rozstrzygnięta (|ocena| < 10 pionów).
Pomijamy momenty, w których wariant silnika pokrywa się z dalszym ciągiem partii (strzałki nic by nie dodały).
Na partię najwyżej MAX_MOMENTS, odstęp ≥ MIN_DISTANCE półruchów, bez ostatnich 2 półruchów (finał opowiada scenariusz).
Dla każdego momentu: wariant silnika z pozycji PO kluczowym ruchu (pierwsze LINE_PLIES półruchów; krócej, gdy mat).
Wariant pokazujemy strzałkami i czyta go system (marker {{v:N}}) — LLM nigdy nie zapisuje tych ruchów sam (zasada nr 1).
"""
from __future__ import annotations

import os
import shutil

import chess
import chess.engine

from pgn_loader import Ply

DEPTH = int(os.environ.get("KEY_ENGINE_DEPTH", "18"))
MAX_MOMENTS = 2
MIN_DISTANCE = 8
LINE_PLIES = 4
SAC_MIN = 3            # punkty materiału (pion 1, lekka 3, wieża 5, hetman 9)
SAC_EVAL_TOL = 50      # centypiony
SAC_MAX_BEFORE = 400   # centypiony: przy większej przewadze grającego nie szukamy ofiar
TURN_MIN = 200
DECIDED = 1000
MATE = 3000
VALUES = {chess.PAWN: 1, chess.KNIGHT: 3, chess.BISHOP: 3, chess.ROOK: 5, chess.QUEEN: 9, chess.KING: 0}


def engine_path() -> str | None:
    return os.environ.get("STOCKFISH_PATH") or shutil.which("stockfish") or (
        "/usr/games/stockfish" if os.path.exists("/usr/games/stockfish") else None)


def _balance(board: chess.Board, color: chess.Color) -> int:
    s = 0
    for p in board.piece_map().values():
        s += VALUES[p.piece_type] * (1 if p.color == color else -1)
    return s


def _cp(info) -> int:
    return info["score"].white().score(mate_score=MATE)


def line_plies(fen: str, moves: list) -> list:
    """Ruchy wariantu jako obiekty Ply (do zapisu słownego w notacji kanału)."""
    board, out = chess.Board(fen), []
    for i, mv in enumerate(moves, start=1):
        san = board.san(mv)
        before = board.fen()
        p = dict(index=i, move_number=board.fullmove_number, color=board.turn, san=san, move=mv,
                 fen_before=before, is_capture=board.is_capture(mv), is_castling=board.is_castling(mv),
                 is_en_passant=board.is_en_passant(mv), gives_check=board.gives_check(mv))
        board.push(mv)
        out.append(Ply(fen_after=board.fen(), is_mate=board.is_checkmate(), **p))
    return out


def detect(game, path: str | None = None, depth: int = DEPTH) -> list:
    """[{"ply": N, "kind": "sacrifice"|"turn", "line": [uci…], "line_san": "…", "eval_before": cp, "eval_after": cp}]"""
    path = path or engine_path()
    if not path:
        return []
    plies = game.plies
    n = len(plies)
    with chess.engine.SimpleEngine.popen_uci(path) as eng:
        limit = chess.engine.Limit(depth=depth)
        ev = [_cp(eng.analyse(chess.Board(game.start_fen), limit))]
        lines = [None]
        for p in plies:
            b = chess.Board(p.fen_after)
            if b.is_checkmate():
                ev.append(MATE if p.color == chess.WHITE else -MATE)
                lines.append([])
                continue
            if b.is_game_over():
                ev.append(0)
                lines.append([])
                continue
            info = eng.analyse(b, limit)
            ev.append(_cp(info))
            lines.append(list(info.get("pv") or []))

    cands = []
    for i, p in enumerate(plies[:-2]):
        sign = 1 if p.color == chess.WHITE else -1
        before, after = ev[i] * sign, ev[i + 1] * sign       # z perspektywy grającego
        if abs(ev[i]) >= DECIDED:
            continue
        b0 = _balance(chess.Board(p.fen_before), p.color)
        losses = [b0 - _balance(chess.Board(plies[j].fen_after), p.color)
                  for j in (i + 1, i + 3, i + 5) if j < n]
        # ofiara ma sens, gdy partia jeszcze się waży (przy dużej przewadze to zwykle tylko wymiany "na dokładkę")
        if losses and min(losses) >= SAC_MIN and after >= before - SAC_EVAL_TOL and before <= SAC_MAX_BEFORE:
            cands.append((2, min(losses) * 100 + after - before, i, "sacrifice"))
        elif abs(after - before) >= TURN_MIN:
            cands.append((1, abs(after - before), i, "turn"))
    cands.sort(reverse=True)

    chosen = []
    for _, _, i, kind in cands:
        if any(abs(i - c[0]) < MIN_DISTANCE for c in chosen):
            continue
        line = lines[i + 1][:LINE_PLIES]
        for j in range(2, len(line)):  # figura wraca tam, skąd przyszła — dalej już tylko "przestawianie"
            if line[j].from_square == line[j - 2].to_square and line[j].to_square == line[j - 2].from_square:
                line = line[:j]
                break
        if not line:
            continue
        game_next = [q.move for q in plies[i + 1:i + 3]]
        if line[:2] == game_next[:len(line[:2])]:  # wariant = dalszy ciąg partii — nic nowego do pokazania
            continue
        chosen.append((i, kind, line))
        if len(chosen) == MAX_MOMENTS:
            break

    out = []
    for i, kind, line in sorted(chosen):
        p = plies[i]
        lp = line_plies(p.fen_after, line)
        out.append({"ply": p.index, "kind": kind, "line": [m.uci() for m in line],
                    "line_san": " ".join(x.san for x in lp), "eval_before": ev[i], "eval_after": ev[i + 1]})
    return out
