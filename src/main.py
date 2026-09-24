"""Budowa odcinka: PGN + scenariusz -> TTS z timestampami -> animacja -> MP4.

Użycie:
  python src/main.py --pgn games/opera_1858.pgn --script scripts/opera_1858.json --out out/opera.mp4
  python src/main.py ... --dry-run      # bez Inworld: cisza + szacowane czasy
  python src/main.py ... --check-only   # tylko walidacja PGN i scenariusza
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from pgn_loader import load_game
from players import catalog_entry, side
from render import Renderer, render_video, schedule
from script_check import Segment, build_segments, load_script
from tts_inworld import dry_run, map_tokens_to_times, synthesize

LEAD_IN = 1.0     # sekundy ciszy na początku (pozycja startowa na ekranie)
TAIL = 3.0        # końcowa pauza z pozycją matową / końcową
DRIFT_WARN = 0.3
# Stałe zakończenie każdego odcinka (czytane przez lektora po scenariuszu)
OUTRO = ("Dziękujemy za obejrzenie. Jeśli interesujecie się szachami, "
         "polubcie ten film i zasubskrybujcie kanał.")  # ostrzeżenie, gdy animacja spóźnia się względem lektora


def build_audio(parts: list, out_wav: Path, workdir: Path) -> None:
    """parts: lista ('file', path) albo ('silence', sekundy). Wszystko do 48k mono PCM."""
    listing = []
    for i, (kind, val) in enumerate(parts):
        wav = workdir / f"part_{i:04d}.wav"
        if kind == "file":
            cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(val), "-ar", "48000", "-ac", "1", str(wav)]
        else:
            cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                   "-t", f"{val:.3f}", str(wav)]
        subprocess.run(cmd, check=True)
        listing.append(f"file '{wav}'")
    lst = workdir / "concat.txt"
    lst.write_text("\n".join(listing), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "pcm_s16le", str(out_wav)], check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pgn", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--cache", default=".tts_cache")
    ap.add_argument("--fps", type=int, default=25)
    args = ap.parse_args()

    game = load_game(args.pgn)
    script = load_script(args.script)
    segments, warnings = build_segments(script, game)
    if OUTRO:
        segments.append(Segment(id="outro", tts_text=OUTRO, tokens=OUTRO.split(), pause_after=0.3))
    for w in warnings:
        print("UWAGA:", w, file=sys.stderr)
    print(f"OK: {len(game.plies)} półruchów, {len(segments)} segmentów")
    if args.check_only:
        for s in segments:
            print(f"--- {s.id}\n{s.tts_text}")
        return 0

    voice_id = os.environ.get("INWORLD_VOICE_ID", "")
    if not args.dry_run and not voice_id:
        print("Brak INWORLD_VOICE_ID", file=sys.stderr)
        return 2

    cache = Path(args.cache)
    parts = [("silence", LEAD_IN)]
    anchor_times = []
    cursor = LEAD_IN
    chapters = []
    for seg in segments:
        if seg.chapter:
            chapters.append({"t": 0.0 if not chapters else round(cursor, 2), "title": seg.chapter})
        res = dry_run(seg.tts_text, cache) if args.dry_run else synthesize(seg.tts_text, cache, voice_id)
        times = map_tokens_to_times(seg.tokens, res)
        for a in seg.anchors:
            anchor_times.append((cursor + times[a.token_index], a.ply_index))
        parts.append(("file", res.audio_path))
        parts.append(("silence", seg.pause_after))
        cursor += res.duration + seg.pause_after
    parts.append(("silence", TAIL))
    duration = cursor + TAIL

    events = schedule(anchor_times, len(game.plies))
    wanted = {p: t for t, p in anchor_times}
    for e in events:
        if e.ply_index in wanted and e.time - wanted[e.ply_index] > DRIFT_WARN:
            print(f"UWAGA: półruch {e.ply_index} spóźniony o {e.time - wanted[e.ply_index]:.2f}s "
                  f"względem lektora — rozdziel markery", file=sys.stderr)

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        wav = Path(tmp) / "voice.wav"
        build_audio(parts, wav, Path(tmp))
        entry = catalog_entry(Path(args.pgn).stem)
        renderer = Renderer(
            game, script.get("title", game.headers.get("Event", "")),
            white=side(entry, "white", game.headers.get("White", "?")),
            black=side(entry, "black", game.headers.get("Black", "?")),
            year=str(entry["year"]) if entry else "",
            caption=(entry or {}).get("label_pl", ""),
        )
        render_video(renderer, events, duration, wav, out, fps=args.fps)
    timing = out.with_suffix(".timing.json")
    timing.write_text(json.dumps({"duration": round(duration, 2), "chapters": chapters},
                                 ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Gotowe: {out} ({duration:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
