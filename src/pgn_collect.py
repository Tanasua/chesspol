"""Zbieranie i krzyżowa weryfikacja PGN dla catalog/games.json (zasada nr 4).

Dla każdej partii z katalogu szuka jej w kilku NIEZALEŻNYCH kolekcjach PGN
(źródło = katalog z plikami .pgn). Partia jest zweryfikowana, gdy co najmniej
MIN_SOURCES różnych źródeł ma identyczny ciąg ruchów, zgodny wynik i kolory,
a liczba ruchów zgadza się z katalogiem (jeśli katalog ją podaje).
Wtedy zapisuje games/<id>.pgn i ustawia pgn_verified w katalogu.

  python src/pgn_collect.py --source pgnmentor=/data/ChessData/PgnMentor \
                            --source famous=/data/famous_games.pgn --source books=/data/ChessPGN
  python src/pgn_collect.py ... --only rotlewi_rubinstein_1907 --dry-run
"""
from __future__ import annotations

import argparse
import io
import json
import re
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

import chess
import chess.pgn

ROOT = Path(__file__).resolve().parent.parent
CATALOG = ROOT / "catalog" / "games.json"
GAMES = ROOT / "games"
MIN_SOURCES = 2

# warianty transkrypcji nazwisk spotykane w bazach
ALIASES = {
    "alekhine": ["aljechin", "alekhin", "aljekhin"],
    "bogoljubov": ["bogoljubow", "bogolyubov", "bogoljubov"],
    "nimzowitsch": ["nimzovich", "nimzowitsch", "niemzowitsch", "nimzovitch"],
    "korchnoi": ["kortschnoj", "korchnoy", "kortchnoi"],
    "yusupov": ["jussupow", "yusupov", "iusupov"],
    "ivanchuk": ["iwantschuk", "ivanchuk"],
    "tartakower": ["tartakover", "tartakower"],
    "chigorin": ["tchigorin", "tschigorin", "chigorin"],
    "levitsky": ["levitzky", "levitsky", "lewitzki"],
    "rotlewi": ["rotlevi", "rotlewi"],
    "nezhmetdinov": ["nezhmetdinov", "nejmetdinov"],
    "beliavsky": ["beliavsky", "belyavsky", "beljavsky"],
    "praggnanandhaa": ["praggnanandhaa", "rameshbabu"],
    "gukesh": ["gukesh", "dommaraju"],
    "nepomniachtchi": ["nepomniachtchi", "nepomnyashchy"],
}


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s)
    return re.sub(r"[^a-z ]", " ", "".join(c for c in s if not unicodedata.combining(c)).lower())


def keys_for(name: str, explicit: list | None = None) -> list:
    """Słowa do dopasowania nagłówka White/Black: jawne klucze z katalogu albo nazwisko (+ warianty)."""
    if explicit:
        return [norm(x).strip() for x in explicit]
    words = [w for w in norm(name).split() if len(w) > 2 and w not in {"the", "and", "von", "van"}]
    last = words[-1] if words else norm(name).strip()
    return sorted({last, *ALIASES.get(last, [])})


def years_for(g: dict) -> set:
    y = int(g["year"])
    return {y - 1, y, y + 1} if g.get("year_span") else {y}


def iter_chunks(path: Path):
    raw = path.read_bytes()
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError:
        text = raw.decode("latin-1")
    for chunk in re.split(r"\n(?=\[Event )", text):
        if "[White " in chunk:
            yield chunk


HDR = re.compile(r'^\[(\w+) "(.*)"\]\s*$', re.M)


def candidates(catalog_games: list, sources: dict) -> dict:
    """{game_id: [(source, sans, result, round)]}"""
    by_year = defaultdict(list)
    for g in catalog_games:
        entry = (g, keys_for(g["white"], g.get("white_keys")), keys_for(g["black"], g.get("black_keys")))
        for y in years_for(g):
            by_year[y].append(entry)
    date_re = re.compile(r'^\[Date "(\d{4})', re.M)
    found = defaultdict(list)
    for src, files in sources.items():
        for path in files:
            for chunk in iter_chunks(path):
                m = date_re.search(chunk, 0, 2000)
                if not m or int(m.group(1)) not in by_year:
                    continue
                h = dict(HDR.findall(chunk[:2000]))
                w, b = norm(h.get("White", "")), norm(h.get("Black", ""))
                for g, wk, bk in by_year[int(m.group(1))]:
                    if not any(k in w for k in wk) or not any(k in b for k in bk):
                        continue
                    game = chess.pgn.read_game(io.StringIO(chunk))
                    if game is None or game.errors:
                        continue
                    sans, board = [], game.board()
                    for mv in game.mainline_moves():
                        sans.append(board.san(mv))
                        board.push(mv)
                    found[g["id"]].append((src, tuple(sans), h.get("Result", "*"), h.get("Round", "?")))
    return found


def _round_no(r) -> int | None:
    m = re.match(r"\s*(\d+)", str(r or ""))
    return int(m.group(1)) if m else None


def plausible(g: dict, sans: tuple, result: str, rnd: str) -> bool:
    if g.get("result") and result not in (g["result"], "*"):
        return False
    want, got = _round_no(g.get("round")), _round_no(rnd)
    if want is not None and got is not None and want != got:
        return False
    if g.get("moves"):
        full = (len(sans) + 1) // 2
        if full != g["moves"]:
            return False
    return bool(sans)


def _final(sans: tuple) -> str:
    board = chess.Board()
    for san in sans:
        board.push_san(san)
    return board.board_fen()


def decide(g: dict, cands: list) -> tuple[str, tuple | None, list]:
    by_moves = defaultdict(set)
    for src, sans, res, rnd in cands:
        if plausible(g, sans, res, rnd):
            by_moves[sans].add(src)
    if not by_moves:
        return ("not_found" if not cands else "no_plausible"), None, []
    if not g.get("moves") and len(by_moves) > 1:
        # bez liczby ruchów w katalogu nie wiadomo, która z kilku partii tej pary jest właściwa
        return "ambiguous", None, sorted(set().union(*by_moves.values()))
    best = max(by_moves.items(), key=lambda kv: len(kv[1]))
    if len(best[1]) >= MIN_SOURCES:
        rivals = [m for m, s in by_moves.items() if m != best[0] and len(s) >= MIN_SOURCES]
        if rivals:
            # różna kolejność ruchów prowadząca do tej samej pozycji końcowej — rozstrzyga większość
            same_end = all(_final(m) == _final(best[0]) for m in rivals)
            if not same_end or any(len(by_moves[m]) >= len(best[1]) for m in rivals):
                return "conflict", None, sorted(best[1])
            return "verified_transposition", best[0], sorted(best[1])
        return "verified", best[0], sorted(best[1])
    return "single_source", None, sorted(best[1])


def write_pgn(g: dict, sans: tuple) -> Path:
    game = chess.pgn.Game()
    game.headers["Event"] = g.get("event") or "?"
    game.headers["Site"] = g.get("site_pl") or g.get("site") or "?"
    game.headers["Date"] = f"{g['year']}.??.??"
    game.headers["Round"] = g.get("round") or "?"
    game.headers["White"] = g["white"]
    game.headers["Black"] = g["black"]
    game.headers["Result"] = g.get("result") or "*"
    node, board = game, game.board()
    for san in sans:
        mv = board.parse_san(san)
        node = node.add_variation(mv)
        board.push(mv)
    path = GAMES / f"{g['id']}.pgn"
    if path.exists():  # nie nadpisuj ręcznie dopracowanych nagłówków, jeśli ruchy są te same
        old = chess.pgn.read_game(io.StringIO(path.read_text(encoding="utf-8")))
        if old is not None and [m for m in old.mainline_moves()] == [m for m in game.mainline_moves()]:
            return path
    path.write_text(str(game) + "\n", encoding="utf-8")
    return path


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--source", action="append", required=True, help="nazwa=ścieżka (plik .pgn lub katalog)")
    ap.add_argument("--only", action="append")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sources = {}
    for s in args.source:
        name, p = s.split("=", 1)
        p = Path(p)
        sources[name] = sorted(p.rglob("*.pgn")) if p.is_dir() else [p]

    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    games = [g for g in catalog["games"] if not args.only or g["id"] in args.only]
    found = candidates(games, sources)

    stats = defaultdict(int)
    for g in games:
        status, sans, srcs = decide(g, found.get(g["id"], []))
        stats[status] += 1
        print(f"{status:14} #{g['n']:>3} {g['id']:45} {','.join(srcs)}")
        if args.dry_run:
            continue
        g["pgn_status"] = status
        g["pgn_sources"] = srcs
        g["pgn_verified"] = status in ("verified", "verified_transposition")
        if sans:
            write_pgn(g, sans)
    print(dict(stats), file=sys.stderr)
    if not args.dry_run:
        CATALOG.write_text(json.dumps(catalog, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
