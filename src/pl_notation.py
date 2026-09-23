"""Zamiana ruchu na polską mowę (TTS) i polską notację (napisy na ekranie).

Polskie oznaczenia figur: K król, H hetman, W wieża, G goniec, S skoczek.
"""
from __future__ import annotations

import chess

PIECE_WORD = {
    chess.KING: "król", chess.QUEEN: "hetman", chess.ROOK: "wieża",
    chess.BISHOP: "goniec", chess.KNIGHT: "skoczek", chess.PAWN: "pion",
}
PIECE_LETTER_PL = {"K": "K", "Q": "H", "R": "W", "B": "G", "N": "S"}
PROMO_WORD = {  # biernik: "promocja na hetmana"
    chess.QUEEN: "hetmana", chess.ROOK: "wieżę",
    chess.BISHOP: "gońca", chess.KNIGHT: "skoczka",
}
FILE_WORD = {"a": "a", "b": "be", "c": "ce", "d": "de",
             "e": "e", "f": "ef", "g": "gie", "h": "ha"}
RANK_WORD = {"1": "jeden", "2": "dwa", "3": "trzy", "4": "cztery",
             "5": "pięć", "6": "sześć", "7": "siedem", "8": "osiem"}


def square_words(sq: int) -> str:
    name = chess.square_name(sq)
    return f"{FILE_WORD[name[0]]} {RANK_WORD[name[1]]}"


def _disambiguation(san: str) -> str:
    """Oznaczenie źródła z SAN (np. 'b' w Nbd7) czytane po polsku: 'z be'."""
    san = san.rstrip("+#")
    if san[0] not in "KQRBN":
        return ""
    body = san[1:].replace("x", "").split("=")[0]
    dis = body[:-2]
    if not dis:
        return ""
    words = [FILE_WORD[c] if c in FILE_WORD else RANK_WORD[c] for c in dis]
    return "z " + " ".join(words)


def spoken(ply) -> str:
    """Tekst do TTS, np. 'skoczek z be bije de siedem, szach'."""
    board = chess.Board(ply.fen_before)
    move = ply.move
    if ply.is_castling:
        text = "krótka roszada" if chess.square_file(move.to_square) == 6 else "długa roszada"
    else:
        piece = board.piece_at(move.from_square)
        target = square_words(move.to_square)
        if piece.piece_type == chess.PAWN:
            if ply.is_capture:
                src = FILE_WORD[chess.square_name(move.from_square)[0]]
                text = f"pion {src} bije {target}"
                if ply.is_en_passant:
                    text += " w przelocie"
            else:
                text = target
            if move.promotion:
                text += f", promocja na {PROMO_WORD[move.promotion]}"
        else:
            parts = [PIECE_WORD[piece.piece_type]]
            dis = _disambiguation(ply.san)
            if dis:
                parts.append(dis)
            parts.append("bije" if ply.is_capture else "na")
            parts.append(target)
            text = " ".join(parts)
    if ply.is_mate:
        text += ", mat"
    elif ply.gives_check:
        text += ", szach"
    return text


def san_pl(san: str) -> str:
    """Nf3 -> Sf3, Qxd7+ -> Hxd7+, e8=Q -> e8=H."""
    out = []
    for i, ch in enumerate(san):
        prev = san[i - 1] if i else ""
        out.append(PIECE_LETTER_PL[ch] if ch in PIECE_LETTER_PL and (i == 0 or prev == "=") else ch)
    return "".join(out)


def label(ply) -> str:
    """'12. O-O-O' albo '12... Wd8' — etykieta ruchu na ekranie."""
    dots = "." if ply.color == chess.WHITE else "..."
    return f"{ply.move_number}{dots} {san_pl(ply.san)}"
