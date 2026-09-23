"""Generowanie scenariusza: PGN -> tabela półruchów -> LLM -> walidacja -> scripts/<nazwa>.json.

Użycie:
  python src/script_gen.py --pgn games/opera_1858.pgn --out scripts/opera_1858.json
  python src/script_gen.py ... --stockfish /usr/games/stockfish   # oceny silnika w tabeli
  python src/script_gen.py ... --table-only                       # tylko wydruk wejścia dla LLM

LLM (OpenAI Responses API, OPENAI_API_KEY) dostaje prompts/script_system_pl.md jako instructions. Wynik przechodzi przez
build_segments (ta sama walidacja co w main.py); przy błędzie model dostaje komunikat
i ma do MAX_FIXES poprawek. Fakty historyczne: tylko nagłówki PGN + facts/<nazwa>.md.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from pathlib import Path

import chess
import chess.engine

from pgn_loader import load_game
from script_check import ScriptError, build_segments

ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = ROOT / "prompts" / "script_system_pl.md"
FACTS_DIR = ROOT / "facts"
DEFAULT_MODEL = os.environ.get("SCRIPT_MODEL", "gpt-5.5")
REASONING_EFFORT = os.environ.get("SCRIPT_REASONING", "high")
MAX_FIXES = 3
ENGINE_DEPTH = 18


def _score_str(score: chess.engine.PovScore) -> str:
    """Ocena z perspektywy białych: '+1.25', '-0.40', '#3', '#-2'."""
    w = score.white()
    if w.is_mate():
        return f"#{w.mate()}"
    return f"{w.score() / 100:+.2f}"


def engine_evals(game, engine_path: str, depth: int = ENGINE_DEPTH) -> list:
    """Ocena pozycji PO każdym półruchu (lista długości len(plies))."""
    out = []
    with chess.engine.SimpleEngine.popen_uci(engine_path) as eng:
        for p in game.plies:
            board = chess.Board(p.fen_after)
            if board.is_checkmate():
                out.append("mat")
                continue
            if board.is_game_over():
                out.append("koniec")
                continue
            info = eng.analyse(board, chess.engine.Limit(depth=depth))
            best = info.get("pv", [None])[0]
            best_san = board.san(best) if best else "?"
            out.append(f"{_score_str(info['score'])} (najlepsza odpowiedź wg silnika: {best_san})")
    return out


def ply_table(game, evals: list | None = None) -> str:
    """N | numer ruchu | kolor | SAN | FEN przed ruchem | ocena po ruchu."""
    rows = ["N | ruch | kolor | SAN | FEN przed ruchem | ocena po ruchu (+ = lepiej dla białych)"]
    for p in game.plies:
        color = "białe" if p.color == chess.WHITE else "czarne"
        ev = evals[p.index - 1] if evals else "brak"
        rows.append(f"{p.index} | {p.move_number} | {color} | {p.san} | {p.fen_before} | {ev}")
    return "\n".join(rows)


def build_user_message(game, name: str, evals: list | None) -> str:
    headers = "\n".join(f"[{k} \"{v}\"]" for k, v in game.headers.items())
    parts = [f"NAGŁÓWKI PGN\n{headers}", f"PÓŁRUCHY (łącznie {len(game.plies)})\n{ply_table(game, evals)}"]
    facts = FACTS_DIR / f"{name}.md"
    if facts.exists():
        parts.append(f"FAKTY (zweryfikowane)\n{facts.read_text(encoding='utf-8').strip()}")
    else:
        parts.append("FAKTY: brak pliku z faktami — używaj wyłącznie nagłówków PGN.")
    if not evals:
        parts.append("OCENY SILNIKA: brak — nie używaj ocen typu \"błąd\", \"najlepszy ruch\".")
    parts.append("Napisz scenariusz odcinka zgodnie z zasadami. Zwróć wyłącznie JSON.")
    return "\n\n".join(parts)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _validate(text: str, game) -> tuple[dict | None, str | None, list]:
    """(scenariusz, błąd, ostrzeżenia)."""
    try:
        script = json.loads(_strip_fences(text))
    except json.JSONDecodeError as e:
        return None, f"Niepoprawny JSON: {e}", []
    if not isinstance(script, dict) or not isinstance(script.get("segments"), list):
        return None, "JSON musi być obiektem z polami \"title\" i \"segments\" (lista).", []
    for i, seg in enumerate(script["segments"]):
        if not isinstance(seg, dict) or not {"id", "text"} <= seg.keys():
            return None, f"Segment nr {i + 1} musi mieć pola \"id\" i \"text\".", []
    try:
        _, warnings = build_segments(script, game)
    except ScriptError as e:
        return None, str(e), []
    return script, None, warnings


SCRIPT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "segments"],
    "properties": {
        "title": {"type": "string"},
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "text", "pause_after"],
                "properties": {
                    "id": {"type": "string"},
                    "text": {"type": "string"},
                    "pause_after": {"type": "number"},
                },
            },
        },
    },
}


def _ask(client, model: str, system: str, messages: list) -> str:
    resp = client.responses.create(
        model=model,
        instructions=system,
        input=messages,
        reasoning={"effort": REASONING_EFFORT},
        text={"format": {"type": "json_schema", "name": "scenariusz", "strict": True, "schema": SCRIPT_SCHEMA}},
        max_output_tokens=32000,
        store=False,
    )
    if resp.status == "incomplete":
        reason = resp.incomplete_details.reason if resp.incomplete_details else None
        raise RuntimeError(f"Odpowiedź niepełna ({reason})")
    for item in resp.output:
        for part in getattr(item, "content", None) or []:
            if part.type == "refusal":
                raise RuntimeError(f"Model odmówił odpowiedzi: {part.refusal}")
    text = resp.output_text
    if not text.strip():
        raise RuntimeError("Pusta odpowiedź modelu")
    return text


def generate(game, name: str, model: str, evals: list | None) -> tuple[dict, list]:
    from openai import OpenAI

    client = OpenAI()  # OPENAI_API_KEY ze środowiska
    system = PROMPT_PATH.read_text(encoding="utf-8")
    messages = [{"role": "user", "content": build_user_message(game, name, evals)}]

    last_err = None
    for attempt in range(1 + MAX_FIXES):
        text = _ask(client, model, system, messages)
        script, err, warnings = _validate(text, game)
        if script is not None:
            return script, warnings
        last_err = err
        print(f"Próba {attempt + 1}: {err}", file=sys.stderr)
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content":
                         f"Walidacja odrzuciła scenariusz:\n{err}\n\n"
                         "Popraw i zwróć cały scenariusz ponownie, wyłącznie JSON."})
    raise ScriptError(f"Brak poprawnego scenariusza po {MAX_FIXES} poprawkach: {last_err}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pgn", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--name", help="nazwa partii dla facts/<name>.md (domyślnie z nazwy PGN)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--stockfish", default=os.environ.get("STOCKFISH_PATH") or shutil.which("stockfish"))
    ap.add_argument("--no-engine", action="store_true")
    ap.add_argument("--table-only", action="store_true")
    ap.add_argument("--force", action="store_true", help="nadpisz istniejący plik")
    args = ap.parse_args()

    game = load_game(args.pgn)
    name = args.name or Path(args.pgn).stem
    out = Path(args.out)
    if out.exists() and not args.force and not args.table_only:
        print(f"{out} już istnieje — użyj --force", file=sys.stderr)
        return 2

    evals = None
    if not args.no_engine:
        if args.stockfish:
            evals = engine_evals(game, args.stockfish)
        else:
            print("UWAGA: brak Stockfisha — tabela bez ocen, LLM nie może oceniać ruchów", file=sys.stderr)

    if args.table_only:
        print(build_user_message(game, name, evals))
        return 0

    script, warnings = generate(game, name, args.model, evals)
    for w in warnings:
        print("UWAGA:", w, file=sys.stderr)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Zapisano: {out} ({len(script['segments'])} segmentów)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
