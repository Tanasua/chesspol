"""Zamiana ruchu na ukraińską mowę (TTS) i zapis na ekranie (ukraiński SAN: Кр Ф Т С К).

Pola czytane nazwami liter: е чотири, еф три (a а, b бе, c це, d де, e е, f еф, g же, h аш).
Przykłady: "кінь еф три", "слон бере еф сім, шах", "е бере де п'ять", "коротка рокіровка".
NIE zweryfikowane przez native speakera — odsłuchać pierwsze odcinki.
"""
from __future__ import annotations

import chess

PIECE_WORD = {chess.KING: "король", chess.QUEEN: "ферзь", chess.ROOK: "тура",
              chess.BISHOP: "слон", chess.KNIGHT: "кінь", chess.PAWN: "пішак"}
PROMO_WORD = {chess.QUEEN: "ферзя", chess.ROOK: "туру", chess.BISHOP: "слона", chess.KNIGHT: "коня"}
FILE_WORD = {"a": "а", "b": "бе", "c": "це", "d": "де", "e": "е", "f": "еф", "g": "же", "h": "аш"}
RANK_WORD = {"1": "один", "2": "два", "3": "три", "4": "чотири", "5": "п'ять", "6": "шість", "7": "сім", "8": "вісім"}
SAN_PIECE = {"K": "Кр", "Q": "Ф", "R": "Т", "B": "С", "N": "К"}

# Zapis ruchu wstawiany jako samodzielna fraza — po przyimku brzmi źle ("після кінь еф три").
PREPOSITIONS = {"на", "після", "до", "від", "з", "із", "зі", "через", "перед", "за", "у", "в", "по"}


def square_words(sq: int) -> str:
    name = chess.square_name(sq)
    return f"{FILE_WORD[name[0]]} {RANK_WORD[name[1]]}"


def _disambiguation(san: str) -> str:
    san = san.rstrip("+#")
    if san[0] not in "KQRBN":
        return ""
    dis = san[1:].replace("x", "").split("=")[0][:-2]
    return "з " + " ".join(FILE_WORD[c] if c.isalpha() else RANK_WORD[c] for c in dis) if dis else ""


def spoken(ply) -> str:
    board = chess.Board(ply.fen_before)
    move = ply.move
    if ply.is_castling:
        text = "коротка рокіровка" if chess.square_file(move.to_square) == 6 else "довга рокіровка"
    else:
        piece = board.piece_at(move.from_square)
        target = square_words(move.to_square)
        if piece.piece_type == chess.PAWN:
            if ply.is_capture:
                text = f"{FILE_WORD[chess.square_name(move.from_square)[0]]} бере {target}"
                if ply.is_en_passant:
                    text += " на проході"
            else:
                text = target
            if move.promotion:
                text += f", перетворення на {PROMO_WORD[move.promotion]}"
        else:
            parts = [PIECE_WORD[piece.piece_type]]
            dis = _disambiguation(ply.san)
            if dis:
                parts.append(dis)
            parts += ["бере", target] if ply.is_capture else [target]
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
