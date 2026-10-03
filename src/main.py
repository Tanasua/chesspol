"""Budowa odcinka: PGN + scenariusz -> TTS z timestampami -> animacja -> MP4.

Użycie:
  python src/main.py --pgn games/opera_1858.pgn --script scripts/opera_1858.json --out out/opera.mp4
  python src/main.py ... --dry-run      # bez TTS: cisza + szacowane czasy
  CHANNEL=de python src/main.py ...     # kanał niemiecki (src/lang.py): zapis ruchów, zwroty, ElevenLabs
  python src/main.py ... --check-only   # tylko walidacja PGN i scenariusza
  python src/main.py ... --no-music     # bez muzyki w tle
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
from lang import L, field_
from phrases import OUTRO, cta_for, intro_for
from players import catalog_entry, side
from render import AUTO_STEP, Renderer, render_video, schedule
from script_check import Segment, build_segments, load_script
from tts_inworld import dry_run, map_tokens_to_times

if L.tts == "elevenlabs":
    from tts_elevenlabs import synthesize
else:
    from tts_inworld import synthesize

LEAD_IN = 1.0     # sekundy ciszy na początku (pozycja startowa na ekranie)
TAIL = 3.0        # końcowa pauza z pozycją matową / końcową
DRIFT_WARN = 0.3
CUT_LEAD = 0.04   # rozcięcie nagrania tyle sekund przed początkiem słowa markera
# Stałe zakończenie każdego odcinka (OUTRO, czytane po scenariuszu) — w src/phrases.py, w języku kanału
# Muzyka w tle: zapętlona, cicho pod lektorem, wyciszana na końcu. MUSIC="" wyłącza.
ROOT = Path(__file__).resolve().parent.parent
MUSIC = os.environ.get("MUSIC", str(ROOT / "assets" / "music" / "the_daily_ostinato.mp3"))
MUSIC_GAIN_DB = float(os.environ.get("MUSIC_GAIN_DB", "-20"))  # utwór ma ok. -16 LUFS -> ok. -36 LUFS w tle
MUSIC_FADE_IN = 2.0
MUSIC_FADE_OUT = 6.0


def build_audio(parts: list, out_wav: Path, workdir: Path) -> None:
    """parts: ('file', path), ('slice', (path, od, do|None)) albo ('silence', sekundy). Wszystko do 48k mono PCM."""
    listing = []
    for i, (kind, val) in enumerate(parts):
        wav = workdir / f"part_{i:04d}.wav"
        if kind == "file":
            cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(val), "-ar", "48000", "-ac", "1", str(wav)]
        elif kind == "slice":  # fragment nagrania (path, od, do|None) — rozcięcie pod przewijanie ruchów
            path, t0, t1 = val
            cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(path), "-ss", f"{t0:.3f}"] \
                + (["-to", f"{t1:.3f}"] if t1 is not None else []) + ["-ar", "48000", "-ac", "1", str(wav)]
        else:
            cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                   "-t", f"{val:.3f}", str(wav)]
        subprocess.run(cmd, check=True)
        listing.append(f"file '{wav}'")
    lst = workdir / "concat.txt"
    lst.write_text("\n".join(listing), encoding="utf-8")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0", "-i", str(lst),
                    "-c", "pcm_s16le", str(out_wav)], check=True)


def mix_music(voice_wav: Path, music: Path, duration: float, out_wav: Path) -> None:
    """Lektor + muzyka (pętla) -> 48k stereo PCM; muzyka narasta na starcie i płynnie cichnie na końcu."""
    fade_out = min(MUSIC_FADE_OUT, duration / 2)
    flt = (f"[1:a]aformat=sample_rates=48000:channel_layouts=stereo,atrim=0:{duration:.3f},"
           f"volume={MUSIC_GAIN_DB}dB,afade=t=in:d={MUSIC_FADE_IN},"
           f"afade=t=out:st={duration - fade_out:.3f}:d={fade_out:.3f}[m];"
           "[0:a]aformat=sample_rates=48000:channel_layouts=stereo[v];"
           "[v][m]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.95[out]")
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(voice_wav), "-stream_loop", "-1", "-i", str(music),
                    "-filter_complex", flt, "-map", "[out]", "-t", f"{duration:.3f}", "-c:a", "pcm_s16le",
                    str(out_wav)], check=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--pgn", required=True)
    ap.add_argument("--script", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--check-only", action="store_true")
    ap.add_argument("--cache", default=".tts_cache")
    ap.add_argument("--fps", type=int, default=25)
    ap.add_argument("--no-music", action="store_true")
    ap.add_argument("--no-sfx", action="store_true", help="bez dźwięku stawiania figur")
    ap.add_argument("--preroll", help="PNG na początek (np. drabinka turnieju) — do końca pierwszego segmentu scenariusza")
    args = ap.parse_args()

    game = load_game(args.pgn)
    script = load_script(args.script)
    segments, warnings = build_segments(script, game)
    entry = catalog_entry(Path(args.pgn).stem)
    intro = intro_for(entry)
    if intro:  # powitanie prowadzącego na samym początku, przed hakiem scenariusza
        segments.insert(0, Segment(id="intro", tts_text=intro, tokens=intro.split(), pause_after=0.6))
    if len(segments) >= 6:  # prośba o łapkę w połowie — przed segmentem z rozdziałem najbliższym środka
        mid = len(segments) // 2
        starts = [i for i, sg in enumerate(segments) if sg.chapter and 2 <= i <= len(segments) - 2]
        at = min(starts, key=lambda i: abs(i - mid)) if starts else mid
        cta = cta_for(entry)
        segments.insert(at, Segment(id="cta", tts_text=cta, tokens=cta.split(), pause_after=0.8))
    if OUTRO:
        segments.append(Segment(id="outro", tts_text=OUTRO, tokens=OUTRO.split(), pause_after=0.3))
    for w in warnings:
        print("UWAGA:", w, file=sys.stderr)
    print(f"OK: {len(game.plies)} półruchów, {len(segments)} segmentów")
    if args.check_only:
        for s in segments:
            print(f"--- {s.id}\n{s.tts_text}")
        return 0

    voice_id = os.environ.get(L.voice_env, "")
    if not args.dry_run and not voice_id:
        print(f"Brak {L.voice_env}", file=sys.stderr)
        return 2

    cache = Path(args.cache)
    parts = [("silence", LEAD_IN)]
    anchor_times = []
    cursor = LEAD_IN
    chapters = []
    preroll_until = None
    for si, seg in enumerate(segments):
        if si == 2 and args.preroll:  # plansza przez powitanie i hak (intro + s01), potem szachownica
            preroll_until = cursor
        if seg.chapter:
            chapters.append({"t": 0.0 if not chapters else round(cursor, 2), "title": seg.chapter})
        res = dry_run(seg.tts_text, cache) if args.dry_run else synthesize(seg.tts_text, cache, voice_id)
        times = map_tokens_to_times(seg.tokens, res)
        # Pominięte półruchy przed markerem przewijamy w tempie AUTO_STEP. Gdy lektor nie daje na to
        # dość czasu, rozcinamy nagranie tuż przed słowem markera i wstawiamy ciszę (muzyka gra dalej).
        clip_pos, shift = 0.0, 0.0
        for a in seg.anchors:
            t_word = times[a.token_index]
            gap = a.ply_index - (anchor_times[-1][1] if anchor_times else 0) - 1
            if gap > 0:
                prev_t = anchor_times[-1][0] if anchor_times else 0.0
                deficit = (gap + 1) * AUTO_STEP - (cursor + shift + t_word - prev_t)
                if deficit > 0.05:
                    cut = max(clip_pos, t_word - CUT_LEAD)
                    if cut > clip_pos:
                        parts.append(("slice", (res.audio_path, clip_pos, cut)))
                    parts.append(("silence", deficit))
                    clip_pos, shift = cut, shift + deficit
            anchor_times.append((cursor + shift + t_word, a.ply_index))
        parts.append(("slice", (res.audio_path, clip_pos, None)) if clip_pos else ("file", res.audio_path))
        parts.append(("silence", seg.pause_after))
        cursor += res.duration + shift + seg.pause_after
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
        if not args.no_sfx and events:  # ciche "tok" w chwili, gdy figura staje na polu
            from render import ANIM_SEC
            from sfx import sfx_track

            fx = sfx_track(events, game.plies, duration, Path(tmp) / "sfx.wav", land_delay=ANIM_SEC * 0.85)
            with_fx = Path(tmp) / "voice_fx.wav"
            subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(wav), "-i", str(fx), "-filter_complex",
                            "[0:a][1:a]amix=inputs=2:duration=first:normalize=0[out]", "-map", "[out]",
                            "-c:a", "pcm_s16le", str(with_fx)], check=True)
            wav = with_fx
        if MUSIC and not args.no_music:
            if Path(MUSIC).exists():
                mixed = Path(tmp) / "mix.wav"
                mix_music(wav, Path(MUSIC), duration, mixed)
                wav = mixed
            else:
                print(f"UWAGA: brak pliku muzyki {MUSIC} — odcinek bez muzyki", file=sys.stderr)
        renderer = Renderer(
            game, script.get("title", game.headers.get("Event", "")),
            white=side(entry, "white", game.headers.get("White", "?")),
            black=side(entry, "black", game.headers.get("Black", "?")),
            year=str(entry["year"]) if entry else "",
            caption=field_(entry, "label") or "",
        )
        if args.preroll and preroll_until is None:
            preroll_until = cursor
        if args.preroll and events and preroll_until > events[0].time:  # ruchy przed końcem planszy — skróć planszę
            preroll_until = max(0.0, events[0].time - 0.3)
        render_video(renderer, events, duration, wav, out, fps=args.fps,
                     preroll=(args.preroll, preroll_until) if args.preroll else None)
    timing = out.with_suffix(".timing.json")
    timing.write_text(json.dumps({"duration": round(duration, 2), "chapters": chapters,
                                  "moves": [[e.ply_index, round(e.time, 2)] for e in events],
                                  "spoken": sorted(p for _, p in anchor_times)},
                                 ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Gotowe: {out} ({duration:.1f}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
