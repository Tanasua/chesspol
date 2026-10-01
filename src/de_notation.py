"""Zamiana ruchu na niemiecką mowę (TTS) i niemiecką notację (napisy na ekranie).

Niemieckie oznaczenia figur: K König, D Dame, T Turm, L Läufer, S Springer.
Litery kolumn zapisane fonetycznie ("eff", "zeh"), żeby lektor czytał je jak nazwy liter.
"""
from __future__ import annotations

import chess

PIECE_WORD = {
    chess.KING: "König", chess.QUEEN: "Dame", chess.ROOK: "Turm",
    chess.BISHOP: "Läufer", chess.KNIGHT: "Springer", chess.PAWN: "Bauer",
}
PIECE_LETTER_DE = {"K": "K", "Q": "D", "R": "T", "B": "L", "N": "S"}
PROMO_WORD = {  # "Umwandlung in eine Dame"
    chess.QUEEN: "eine Dame", chess.ROOK: "einen Turm",
    chess.BISHOP: "einen Läufer", chess.KNIGHT: "einen Springer",
}
FILE_WORD = {"a": "a", "b": "be", "c": "zeh", "d": "de",
             "e": "e", "f": "eff", "g": "ge", "h": "ha"}
RANK_WORD = {"1": "eins", "2": "zwei", "3": "drei", "4": "vier",
             "5": "fünf", "6": "sechs", "7": "sieben", "8": "acht"}

# Zapis ruchu jest wstawiany jako samodzielna fraza ("Springer nach eff drei") — po przyimku
# wymagającym celownika/biernika ("mit Springer…") zdanie byłoby niegramatyczne.
PREPOSITIONS = {"mit", "nach", "vor", "auf", "durch", "für", "gegen", "ohne", "um", "von", "vom", "zu", "zum",
                "zur", "bei", "beim", "aus", "seit", "über", "unter", "neben", "zwischen", "wegen", "trotz",
                "statt", "dank", "in", "im", "an", "am", "bis"}


def square_words(sq: int) -> str:
    name = chess.square_name(sq)
    return f"{FILE_WORD[name[0]]} {RANK_WORD[name[1]]}"


def _disambiguation(san: str) -> str:
    """Oznaczenie źródła z SAN (np. 'b' w Nbd7): 'von be'."""
    san = san.rstrip("+#")
    if san[0] not in "KQRBN":
        return ""
    body = san[1:].replace("x", "").split("=")[0]
    dis = body[:-2]
    if not dis:
        return ""
    return "von " + " ".join(FILE_WORD[c] if c in FILE_WORD else RANK_WORD[c] for c in dis)


def spoken(ply) -> str:
    """Tekst do TTS, np. 'Springer von be schlägt auf de sieben, Schach'."""
    board = chess.Board(ply.fen_before)
    move = ply.move
    if ply.is_castling:
        text = "kurze Rochade" if chess.square_file(move.to_square) == 6 else "lange Rochade"
    else:
        piece = board.piece_at(move.from_square)
        target = square_words(move.to_square)
        if piece.piece_type == chess.PAWN:
            if ply.is_capture:
                src = FILE_WORD[chess.square_name(move.from_square)[0]]
                text = f"Bauer {src} schlägt auf {target}"
                if ply.is_en_passant:
                    text += " en passant"
            else:
                text = target
            if move.promotion:
                text += f", Umwandlung in {PROMO_WORD[move.promotion]}"
        else:
            parts = [PIECE_WORD[piece.piece_type]]
            dis = _disambiguation(ply.san)
            if dis:
                parts.append(dis)
            parts += ["schlägt auf", target] if ply.is_capture else ["nach", target]
            text = " ".join(parts)
    if ply.is_mate:
        text += ", Matt"
    elif ply.gives_check:
        text += ", Schach"
    return text


def san_local(san: str) -> str:
    """Nf3 -> Sf3, Qxd7+ -> Dxd7+, e8=Q -> e8=D."""
    out = []
    for i, ch in enumerate(san):
        prev = san[i - 1] if i else ""
        out.append(PIECE_LETTER_DE[ch] if ch in PIECE_LETTER_DE and (i == 0 or prev == "=") else ch)
    return "".join(out)


def label(ply) -> str:
    """'12. O-O-O' albo '12... Td8' — etykieta ruchu na ekranie."""
    dots = "." if ply.color == chess.WHITE else "..."
    return f"{ply.move_number}{dots} {san_local(ply.san)}"
