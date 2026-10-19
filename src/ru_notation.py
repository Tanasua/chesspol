"""Zamiana ruchu na rosyjską mowę (TTS) i zapis na ekranie (rosyjski SAN: Кр Ф Л С К).

Pola czytane nazwami liter: е четыре, эф три (a а, b бэ, c цэ, d дэ, e е, f эф, g жэ, h аш).
Przykłady: "конь эф три", "слон берёт эф семь, шах", "е берёт дэ пять", "короткая рокировка".
NIE zweryfikowane przez native speakera — odsłuchać pierwsze odcinki.
"""
from __future__ import annotations

import chess

PIECE_WORD = {chess.KING: "король", chess.QUEEN: "ферзь", chess.ROOK: "ладья",
              chess.BISHOP: "слон", chess.KNIGHT: "конь", chess.PAWN: "пешка"}
PROMO_WORD = {chess.QUEEN: "ферзя", chess.ROOK: "ладью", chess.BISHOP: "слона", chess.KNIGHT: "коня"}
FILE_WORD = {"a": "а", "b": "бэ", "c": "цэ", "d": "дэ", "e": "е", "f": "эф", "g": "жэ", "h": "аш"}
RANK_WORD = {"1": "один", "2": "два", "3": "три", "4": "четыре", "5": "пять", "6": "шесть", "7": "семь", "8": "восемь"}
SAN_PIECE = {"K": "Кр", "Q": "Ф", "R": "Л", "B": "С", "N": "К"}

# Zapis ruchu wstawiany jako samodzielna fraza — po przyimku brzmi źle ("после конь эф три").
PREPOSITIONS = {"на", "после", "до", "от", "с", "со", "из", "через", "перед", "за", "в", "во", "по"}


def square_words(sq: int) -> str:
    name = chess.square_name(sq)
    return f"{FILE_WORD[name[0]]} {RANK_WORD[name[1]]}"


def _disambiguation(san: str) -> str:
    san = san.rstrip("+#")
    if san[0] not in "KQRBN":
        return ""
    dis = san[1:].replace("x", "").split("=")[0][:-2]
    return "с " + " ".join(FILE_WORD[c] if c.isalpha() else RANK_WORD[c] for c in dis) if dis else ""


def spoken(ply) -> str:
    board = chess.Board(ply.fen_before)
    move = ply.move
    if ply.is_castling:
        text = "короткая рокировка" if chess.square_file(move.to_square) == 6 else "длинная рокировка"
    else:
        piece = board.piece_at(move.from_square)
        target = square_words(move.to_square)
        if piece.piece_type == chess.PAWN:
            if ply.is_capture:
                text = f"{FILE_WORD[chess.square_name(move.from_square)[0]]} берёт {target}"
                if ply.is_en_passant:
                    text += " на проходе"
            else:
                text = target
            if move.promotion:
                text += f", превращение в {PROMO_WORD[move.promotion]}"
        else:
            parts = [PIECE_WORD[piece.piece_type]]
            dis = _disambiguation(ply.san)
            if dis:
                parts.append(dis)
            parts += ["берёт", target] if ply.is_capture else [target]
            text = " ".join(parts)
    if ply.is_mate:
        text += ", мат"
    elif ply.gives_check:
        text += ", шах"
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
