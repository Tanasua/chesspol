"""Zamiana ruchu na turecką mowę (TTS) i zapis na ekranie (turecki SAN: Ş V K F A).

Pola: litera + liczba ("fe üç"); ruch do pola — celownik ("At fe üçe"), bicie — biernik ("Fil fe yediyi alır").
Przykłady: "e dört", "At fe üçe", "Fil fe yediyi alır, şah", "e piyonu de beşi alır", "kısa rok".
NIE zweryfikowane przez native speakera — odsłuchać pierwsze odcinki.
"""
from __future__ import annotations

import chess

PIECE_WORD = {chess.KING: "Şah", chess.QUEEN: "Vezir", chess.ROOK: "Kale",
              chess.BISHOP: "Fil", chess.KNIGHT: "At", chess.PAWN: "piyon"}
PROMO_WORD = {chess.QUEEN: "vezire", chess.ROOK: "kaleye", chess.BISHOP: "file", chess.KNIGHT: "ata"}
FILE_WORD = {"a": "a", "b": "be", "c": "ce", "d": "de", "e": "e", "f": "fe", "g": "ge", "h": "ha"}
RANK_WORD = {"1": "bir", "2": "iki", "3": "üç", "4": "dört", "5": "beş", "6": "altı", "7": "yedi", "8": "sekiz"}
RANK_DAT = {"1": "bire", "2": "ikiye", "3": "üçe", "4": "dörde", "5": "beşe", "6": "altıya", "7": "yediye", "8": "sekize"}
RANK_ACC = {"1": "biri", "2": "ikiyi", "3": "üçü", "4": "dördü", "5": "beşi", "6": "altıyı", "7": "yediyi", "8": "sekizi"}
SAN_PIECE = {"K": "Ş", "Q": "V", "R": "K", "B": "F", "N": "A"}

PREPOSITIONS: set = set()  # turecki ma poimki po wyrazie — brak przyimków przed zapisem ruchu


def square_words(sq: int, case: dict = RANK_WORD) -> str:
    name = chess.square_name(sq)
    return f"{FILE_WORD[name[0]]} {case[name[1]]}"


def _disambiguation(san: str) -> str:
    san = san.rstrip("+#")
    if san[0] not in "KQRBN":
        return ""
    dis = san[1:].replace("x", "").split("=")[0][:-2]
    return " ".join(FILE_WORD[c] if c.isalpha() else RANK_WORD[c] for c in dis) if dis else ""


def spoken(ply) -> str:
    board = chess.Board(ply.fen_before)
    move = ply.move
    if ply.is_castling:
        text = "kısa rok" if chess.square_file(move.to_square) == 6 else "uzun rok"
    else:
        piece = board.piece_at(move.from_square)
        if piece.piece_type == chess.PAWN:
            if ply.is_capture:
                src = FILE_WORD[chess.square_name(move.from_square)[0]]
                text = f"{src} piyonu {square_words(move.to_square, RANK_ACC)} alır"
                if ply.is_en_passant:
                    text += " (geçerken alma)"
            else:
                text = square_words(move.to_square)
            if move.promotion:
                text += f", {PROMO_WORD[move.promotion]} terfi"
        else:
            head = PIECE_WORD[piece.piece_type]
            dis = _disambiguation(ply.san)
            if dis:
                head += f" ({dis})"
            text = (f"{head} {square_words(move.to_square, RANK_ACC)} alır" if ply.is_capture
                    else f"{head} {square_words(move.to_square, RANK_DAT)}")
    if ply.is_mate:
        text += ", şah mat"
    elif ply.gives_check:
        text += ", şah"
    return text


def san_local(san: str) -> str:
    if san.startswith("O-O"):
        return san
    out = SAN_PIECE.get(san[0], san[0]) + san[1:] if san[0] in SAN_PIECE else san
    if "=" in out:
        i = out.index("=")
        out = out[:i + 1] + SAN_PIECE.get(out[i + 1], out[i + 1]) + out[i + 2:]
    return out


def label(ply) -> str:
    dots = "." if ply.color == chess.WHITE else "..."
    return f"{ply.move_number}{dots} {san_local(ply.san)}"
