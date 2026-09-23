"""Wczytanie i walidacja partii PGN. Każdy półruch -> Ply z pełnym kontekstem."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import chess
import chess.pgn


@dataclass(frozen=True)
class Ply:
    index: int            # 1-based numer półruchu
    move_number: int      # numer ruchu w notacji (1. e4 e5 -> oba mają 1)
    color: bool           # chess.WHITE / chess.BLACK
    san: str
    move: chess.Move
    fen_before: str
    fen_after: str
    is_capture: bool
    is_castling: bool
    is_en_passant: bool
    gives_check: bool
    is_mate: bool


@dataclass(frozen=True)
class Game:
    headers: dict
    plies: list
    start_fen: str


class PGNError(ValueError):
    pass


def load_game(path) -> Game:
    with open(path, encoding="utf-8") as fh:
        game = chess.pgn.read_game(fh)
    if game is None:
        raise PGNError(f"Brak partii w pliku {path}")
    if game.errors:
        # python-chess zbiera błędy parsowania zamiast rzucać wyjątek
        raise PGNError(f"Błędy PGN w {path}: {game.errors}")

    board = game.board()
    start_fen = board.fen()
    plies = []
    for i, move in enumerate(game.mainline_moves(), start=1):
        if move not in board.legal_moves:
            raise PGNError(f"Nielegalny ruch nr {i}: {move.uci()}")
        san = board.san(move)
        fen_before = board.fen()
        move_number = board.fullmove_number
        color = board.turn
        is_capture = board.is_capture(move)
        is_castling = board.is_castling(move)
        is_en_passant = board.is_en_passant(move)
        gives_check = board.gives_check(move)
        board.push(move)
        plies.append(Ply(
            index=i, move_number=move_number, color=color, san=san, move=move,
            fen_before=fen_before, fen_after=board.fen(),
            is_capture=is_capture, is_castling=is_castling,
            is_en_passant=is_en_passant, gives_check=gives_check,
            is_mate=board.is_checkmate(),
        ))

    if not plies:
        raise PGNError("Partia nie zawiera ruchów")

    headers = dict(game.headers)
    result = headers.get("Result", "*")
    if plies[-1].is_mate:
        expected = "1-0" if plies[-1].color == chess.WHITE else "0-1"
        if result not in (expected, "*"):
            raise PGNError(f"Wynik w nagłówku {result} nie zgadza się z matem ({expected})")
    return Game(headers=headers, plies=plies, start_fen=start_fen)
