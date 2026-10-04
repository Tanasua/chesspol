"""Zamiana ruchu na mowę w hindi (TTS) i zapis na ekranie (standardowy SAN: K Q R B N).

Nazwy figur: HI_PIECES=hindi (domyślnie; jak w hindi wersji chess.com: राजा, रानी, हाथी, ऊँट, घोड़ा, प्यादा)
albo HI_PIECES=english (zapożyczenia: किंग, क्वीन, रूक, बिशप, नाइट). NIE zweryfikowane przez native speakera —
przed startem kanału odsłuchać i ewentualnie przełączyć styl.
Pola: nazwy liter kolumn po angielsku zapisane dewanagari (ई चार = e4), liczby słownie w hindi.
"""
from __future__ import annotations

import os

import chess

STYLE = os.environ.get("HI_PIECES", "hindi").strip().lower()
PIECE_WORD = ({
    chess.KING: "किंग", chess.QUEEN: "क्वीन", chess.ROOK: "रूक",
    chess.BISHOP: "बिशप", chess.KNIGHT: "नाइट", chess.PAWN: "प्यादा",
} if STYLE == "english" else {
    chess.KING: "राजा", chess.QUEEN: "रानी", chess.ROOK: "हाथी",
    chess.BISHOP: "ऊँट", chess.KNIGHT: "घोड़ा", chess.PAWN: "प्यादा",
})
FILE_WORD = {"a": "ए", "b": "बी", "c": "सी", "d": "डी", "e": "ई", "f": "एफ़", "g": "जी", "h": "एच"}
RANK_WORD = {"1": "एक", "2": "दो", "3": "तीन", "4": "चार", "5": "पाँच", "6": "छह", "7": "सात", "8": "आठ"}
CAPTURES = "पर काटता है"      # "bije na …"
CHECK, MATE = "शह", "शह और मात"
CASTLE_K, CASTLE_Q = "कैसलिंग, राजा की तरफ़", "कैसलिंग, रानी की तरफ़"

# Zapis ruchu wstawiany jako samodzielna fraza; dopełniacz tuż przed nim brzmi źle.
PREPOSITIONS = {"का", "की", "के"}


def square_words(sq: int) -> str:
    name = chess.square_name(sq)
    return f"{FILE_WORD[name[0]]} {RANK_WORD[name[1]]}"


def _disambiguation(san: str) -> str:
    """Źródło z SAN (np. 'b' w Nbd7) -> 'बी वाला' (ten z kolumny b)."""
    san = san.rstrip("+#")
    if san[0] not in "KQRBN":
        return ""
    dis = san[1:].replace("x", "").split("=")[0][:-2]
    if not dis:
        return ""
    return " ".join(FILE_WORD[c] if c.isalpha() else RANK_WORD[c] for c in dis) + " वाला"


def spoken(ply) -> str:
    """Tekst do TTS, np. 'बी वाला घोड़ा डी सात पर काटता है, शह'."""
    board = chess.Board(ply.fen_before)
    move = ply.move
    if ply.is_castling:
        text = CASTLE_K if chess.square_file(move.to_square) == 6 else CASTLE_Q
    else:
        piece = board.piece_at(move.from_square)
        target = square_words(move.to_square)
        if piece.piece_type == chess.PAWN:
            if ply.is_capture:
                src = FILE_WORD[chess.square_name(move.from_square)[0]]
                text = f"{src} {PIECE_WORD[chess.PAWN]} {target} {CAPTURES}"
                if ply.is_en_passant:
                    text += " (आं पासां)"
            else:
                text = target
            if move.promotion:
                text += f", और {PIECE_WORD[move.promotion]} बनता है"
        else:
            dis = _disambiguation(ply.san)
            head = f"{dis} {PIECE_WORD[piece.piece_type]}" if dis else PIECE_WORD[piece.piece_type]
            text = f"{head} {target} {CAPTURES}" if ply.is_capture else f"{head} {target}"
    if ply.is_mate:
        text += f", {MATE}"
    elif ply.gives_check:
        text += f", {CHECK}"
    return text


def san_local(san: str) -> str:
    return san


def label(ply) -> str:
    """'12. O-O-O' albo '12... Rd8' — etykieta ruchu na ekranie (standardowy SAN)."""
    dots = "." if ply.color == chess.WHITE else "..."
    return f"{ply.move_number}{dots} {ply.san}"
