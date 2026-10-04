"""Generowanie scenariusza: PGN -> tabela półruchów -> LLM -> walidacja -> scripts/<nazwa>.json.

Użycie:
  python src/script_gen.py --pgn games/opera_1858.pgn --out scripts/opera_1858.json
  python src/script_gen.py ... --stockfish /usr/games/stockfish   # oceny silnika w tabeli
  python src/script_gen.py ... --table-only                       # tylko wydruk wejścia dla LLM

LLM (OpenAI Responses API, OPENAI_API_KEY) dostaje prompt kanału (prompts/script_system_<język>.md, CHANNEL) jako instructions. Wynik przechodzi przez
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

from lang import L, field_
from pgn_loader import load_game
from script_check import ScriptError, build_segments

ROOT = Path(__file__).resolve().parent.parent
PROMPT_PATH = L.prompt
FACTS_DIR = ROOT / "facts"
CATALOG = ROOT / "catalog" / "games.json"
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
                out.append(L.t["mate"])
                continue
            if board.is_game_over():
                out.append(L.t["over"])
                continue
            info = eng.analyse(board, chess.engine.Limit(depth=depth))
            best = info.get("pv", [None])[0]
            best_san = board.san(best) if best else "?"
            out.append(f"{_score_str(info['score'])} ({L.t['engine_best']}: {best_san})")
    return out


def ply_table(game, evals: list | None = None) -> str:
    """N | numer ruchu | kolor | SAN | FEN przed ruchem | ocena po ruchu."""
    rows = [L.t["table_head"]]
    for p in game.plies:
        color = L.t["white_side"] if p.color == chess.WHITE else L.t["black_side"]
        ev = evals[p.index - 1] if evals else L.t["none"]
        rows.append(f"{p.index} | {p.move_number} | {color} | {p.san} | {p.fen_before} | {ev}")
    return "\n".join(rows)


def catalog_facts(name: str) -> str:
    from players import catalog_entry

    g = catalog_entry(name)
    if not g:
        return ""
    t = L.t
    rows = [(t["white"], field_(g, "white")), (t["black"], field_(g, "black")),
            (t["year"], g.get("year")), (t["event"], field_(g, "event")),
            (t["place"], field_(g, "site")), (t["round"], g.get("round")), (t["result"], g.get("result")),
            (t["nickname"], g.get("nickname")), (t["notes"], g.get("note"))]
    return "\n".join(f"{k}: {v}" for k, v in rows if v)


KM_TEXT = {
    "pl": ("KLUCZOWE MOMENTY (wyznaczone silnikiem; każdy MUSI dostać marker {{v:N}} raz, zaraz po markerze półruchu N):",
           {"sacrifice": "ofiara (materiał oddany, ocena silnika nie spada)", "turn": "zwrot w ocenie silnika"},
           "wariant silnika po tym ruchu"),
    "de": ("SCHLÜSSELMOMENTE (von der Engine bestimmt; jeder MUSS genau einmal den Marker {{v:N}} bekommen, direkt nach dem Marker von Halbzug N):",
           {"sacrifice": "Opfer (Material gegeben, Engine-Bewertung fällt nicht)", "turn": "Wende in der Engine-Bewertung"},
           "Engine-Variante nach diesem Zug"),
    "en": ("KEY MOMENTS (found by the engine; each MUST get the marker {{v:N}} once, right after the marker of half-move N):",
           {"sacrifice": "sacrifice (material given up, engine evaluation does not drop)", "turn": "turning point in the engine evaluation"},
           "engine line after this move"),
}


def key_moments_text(game, moments: list) -> str:
    head, kinds, line = KM_TEXT[L.code]
    rows = [head]
    for km in moments:
        p = game.plies[km["ply"] - 1]
        rows.append(f"N={km['ply']} ({p.san}) — {kinds[km['kind']]}; {line}: {km['line_san']} "
                    f"[{km['eval_before'] / 100:+.2f} -> {km['eval_after'] / 100:+.2f}]")
    return "\n".join(rows)


def build_user_message(game, name: str, evals: list | None, moments: list | None = None) -> str:
    headers = "\n".join(f"[{k} \"{v}\"]" for k, v in game.headers.items())
    t = L.t
    parts = [f"{t['pgn_headers']}\n{headers}", f"{t['plies'].format(n=len(game.plies))}\n{ply_table(game, evals)}"]
    facts = FACTS_DIR / f"{name}.md"
    cat = catalog_facts(name)
    if facts.exists():
        parts.append(f"{t['facts']}\n{facts.read_text(encoding='utf-8').strip()}")
    if cat:
        parts.append(f"{t['catalog_facts']}\n{cat}")
    if not facts.exists() and not cat:
        parts.append(t["no_facts"])
    if not evals:
        parts.append(t["no_engine"])
    if moments:
        parts.append(key_moments_text(game, moments))
    parts.append(t["write"])
    return "\n\n".join(parts)


def _strip_fences(text: str) -> str:
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else ""
        if t.rstrip().endswith("```"):
            t = t.rstrip()[:-3]
    return t.strip()


def _validate(text: str, game, moments: list | None = None) -> tuple[dict | None, str | None, list]:
    """(scenariusz, błąd, ostrzeżenia). moments — kluczowe momenty silnika, dołączane do scenariusza (nie od LLM)."""
    try:
        script = json.loads(_strip_fences(text))
    except json.JSONDecodeError as e:
        return None, f"Niepoprawny JSON: {e}", []
    if isinstance(script, dict):
        script["key_moments"] = moments or []
    if not isinstance(script, dict) or not isinstance(script.get("segments"), list):
        return None, "JSON musi być obiektem z polami \"title\" i \"segments\" (lista).", []
    for i, seg in enumerate(script["segments"]):
        if not isinstance(seg, dict) or not {"id", "text"} <= seg.keys():
            return None, f"Segment nr {i + 1} musi mieć pola \"id\" i \"text\".", []
    hook = script.get("hook")
    if not isinstance(hook, dict) or not (hook.get("text") or "").strip():
        return None, "Pole \"hook\" jest puste — 1–2 zdania na sam początek odcinka + \"ply\" (pozycja kluczowa).", []
    if not (script.get("kicker") or "").strip():
        return None, "Pole \"kicker\" jest puste — 1–3 słowa WERSALIKAMI z wykrzyknikiem (np. \"NIESAMOWITE!\").", []
    try:
        _, warnings = build_segments(script, game)
    except ScriptError as e:
        return None, str(e), []
    return script, None, warnings


SCRIPT_SCHEMA = {
    "type": "object",
    "additionalProperties": False,
    "required": ["hook", "kicker", "title", "description", "segments"],
    "properties": {
        "hook": {
            "type": "object",
            "additionalProperties": False,
            "required": ["text", "ply"],
            "properties": {"text": {"type": "string"}, "ply": {"type": "integer"}},
        },
        "kicker": {"type": "string"},
        "title": {"type": "string"},
        "description": {"type": "string"},
        "segments": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "required": ["id", "text", "pause_after", "chapter"],
                "properties": {
                    "id": {"type": "string"},
                    "chapter": {"type": "string"},
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


def generate(game, name: str, model: str, evals: list | None, moments: list | None = None) -> tuple[dict, list]:
    from openai import OpenAI

    client = OpenAI()  # OPENAI_API_KEY ze środowiska
    system = PROMPT_PATH.read_text(encoding="utf-8")
    messages = [{"role": "user", "content": build_user_message(game, name, evals, moments)}]

    last_err = None
    for attempt in range(1 + MAX_FIXES):
        text = _ask(client, model, system, messages)
        script, err, warnings = _validate(text, game, moments)
        if script is not None:
            return script, warnings
        last_err = err
        print(f"Próba {attempt + 1}: {err}", file=sys.stderr)
        messages.append({"role": "assistant", "content": text})
        messages.append({"role": "user", "content": L.t["fix"].format(err=err)})
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

    evals, moments = None, []
    if not args.no_engine:
        if args.stockfish:
            evals = engine_evals(game, args.stockfish)
            from key_moments import detect

            moments = detect(game, args.stockfish)
            for km in moments:
                print(f"Kluczowy moment: półruch {km['ply']} ({km['kind']}), wariant: {km['line_san']}")
        else:
            print("UWAGA: brak Stockfisha — tabela bez ocen, LLM nie może oceniać ruchów", file=sys.stderr)

    if args.table_only:
        print(build_user_message(game, name, evals, moments))
        return 0

    script, warnings = generate(game, name, args.model, evals, moments)
    for w in warnings:
        print("UWAGA:", w, file=sys.stderr)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(script, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Zapisano: {out} ({len(script['segments'])} segmentów)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
