"""Generuje catalog/LISTA.md (czytelna lista partii ze statusem PGN) z catalog/games.json."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STATUS = {"verified": "✅", "verified_transposition": "✅", "single_source": "1 źródło",
          "conflict": "konflikt", "ambiguous": "niejednoznaczne", "no_plausible": "niezgodne", "not_found": "brak PGN"}


def main() -> None:
    games = json.loads((ROOT / "catalog" / "games.json").read_text(encoding="utf-8"))["games"]
    lines = ["# 100 partii — kolejność publikacji", "",
             "Źródło prawdy: `games.json`. Ten plik generuje `python src/catalog_list.py`.", "",
             "| # | Białe – Czarne | Rok | Wydarzenie | Wynik | PGN | Uwagi |", "|---|---|---|---|---|---|---|"]
    for g in sorted(games, key=lambda g: g["n"]):
        who = f"{g.get('white_pl') or g['white']} – {g.get('black_pl') or g['black']}"
        st = STATUS.get(g.get("pgn_status"), "—")
        note = "; ".join(x for x in ((g.get("nickname") or ""), ("SPORNA" if g.get("disputed") else ""), g.get("note") or "") if x)
        lines.append(f"| {g['n']} | {who} | {g['year']} | {g.get('event') or ''} ({g.get('site_pl') or g.get('site')}) | {g.get('result')} | {st} | {note} |")
    ok = sum(g.get("pgn_verified", False) for g in games)
    lines += ["", f"Gotowe do publikacji (PGN z ≥2 niezależnych baz): **{ok}/100**."]
    (ROOT / "catalog" / "LISTA.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
