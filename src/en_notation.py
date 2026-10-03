"""Zamiana ruchu na angielską mowę (TTS) i zapis na ekranie (standardowy SAN: K Q R B N).

Litery kolumn wielkie ("E four", "Knight to F three"), żeby lektor czytał je jak nazwy liter,
a nie jak przedimek "a" czy słowo "be".
"""
from __future__ import annotations

import chess

PIECE_WORD = {
    chess.KING: "king", chess.QUEEN: "queen", chess.ROOK: "rook",
    chess.BISHOP: "bishop", chess.KNIGHT: "knight", chess.PAWN: "pawn",
}
PROMO_WORD = {chess.QUEEN: "a queen", chess.ROOK: "a rook", chess.BISHOP: "a bishop", chess.KNIGHT: "a knight"}
RANK_WORD = {"1": "one", "2": "two", "3": "three", "4": "four",
             "5": "five", "6": "six", "7": "seven", "8": "eight"}

# Zapis ruchu jest wstawiany jako samodzielna fraza ("knight to F three") — po przyimku brzmi źle.
PREPOSITIONS = {"after", "with", "by", "to", "from", "on", "in", "into", "onto", "for", "of", "at", "against",
                "via", "following", "before", "than", "like", "about", "through", "toward", "towards"}


def square_words(sq: int) -> str:
    name = chess.square_name(sq)
    return f"{name[0].upper()} {RANK_WORD[name[1]]}"


def _disambiguation(san: str) -> str:
    """Oznaczenie źródła z SAN (np. 'b' w Nbd7): 'from B'."""
    san = san.rstrip("+#")
    if san[0] not in "KQRBN":
        return ""
    body = san[1:].replace("x", "").split("=")[0]
    dis = body[:-2]
    if not dis:
        return ""
    return "from " + " ".join(c.upper() if c.isalpha() else RANK_WORD[c] for c in dis)


def spoken(ply) -> str:
    """Tekst do TTS, np. 'knight from B takes D seven, check'."""
    board = chess.Board(ply.fen_before)
    move = ply.move
    if ply.is_castling:
        text = "castles kingside" if chess.square_file(move.to_square) == 6 else "castles queenside"
    else:
        piece = board.piece_at(move.from_square)
        target = square_words(move.to_square)
        if piece.piece_type == chess.PAWN:
            if ply.is_capture:
                src = chess.square_name(move.from_square)[0].upper()
                text = f"{src} takes {target}"
                if ply.is_en_passant:
                    text += " en passant"
            else:
                text = target
            if move.promotion:
                text += f", promoting to {PROMO_WORD[move.promotion]}"
        else:
            parts = [PIECE_WORD[piece.piece_type]]
            dis = _disambiguation(ply.san)
            if dis:
                parts.append(dis)
            parts += ["takes", target] if ply.is_capture else ["to", target]
            text = " ".join(parts)
    if ply.is_mate:
        text += ", checkmate"
    elif ply.gives_check:
        text += ", check"
    return text


def san_local(san: str) -> str:
    return san


def label(ply) -> str:
    """'12. O-O-O' albo '12... Rd8' — etykieta ruchu na ekranie."""
    dots = "." if ply.color == chess.WHITE else "..."
    return f"{ply.move_number}{dots} {ply.san}"
