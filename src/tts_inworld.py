"""Klient Inworld TTS (POST /tts/v1/voice) z timestampami słów i cache na dysku.

Polski jest w Tier 1 dla inworld-tts-2, a także obsługiwany przez inworld-tts-1.5-*.
"""
from __future__ import annotations

import base64
import difflib
import hashlib
import json
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path

import requests

API_URL = "https://api.inworld.ai/tts/v1/voice"
DEFAULT_MODEL = os.environ.get("INWORLD_MODEL", "inworld-tts-2")
DEFAULT_LANGUAGE = os.environ.get("INWORLD_LANGUAGE", "pl-PL")


@dataclass
class TTSResult:
    audio_path: Path
    duration: float
    words: list
    starts: list
    ends: list


def _probe_duration(path: Path) -> float:
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=nw=1:nk=1", str(path)],
        capture_output=True, text=True, check=True,
    ).stdout.strip()
    return float(out)


def synthesize(text: str, cache_dir: Path, voice_id: str, model: str = DEFAULT_MODEL,
               language: str = DEFAULT_LANGUAGE, delivery_mode: str = "BALANCED",
               retries: int = 3) -> TTSResult:
    api_key = os.environ.get("INWORLD_API_KEY")
    if not api_key:
        raise RuntimeError("Brak INWORLD_API_KEY")

    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps([text, voice_id, model, language, delivery_mode]).encode()).hexdigest()[:16]
    audio_path = cache_dir / f"{key}.mp3"
    meta_path = cache_dir / f"{key}.json"

    if not (audio_path.exists() and meta_path.exists()):
        body = {
            "text": text,
            "voiceId": voice_id,
            "modelId": model,
            "audioConfig": {"audioEncoding": "MP3"},
            "timestampType": "WORD",
        }
        if model.startswith("inworld-tts-2"):
            body["language"] = language
            body["deliveryMode"] = delivery_mode
        headers = {"Authorization": f"Basic {api_key}", "Content-Type": "application/json"}

        last_err = None
        for attempt in range(retries):
            try:
                r = requests.post(API_URL, json=body, headers=headers, timeout=120)
                if r.status_code == 429 or r.status_code >= 500:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
                r.raise_for_status()
                data = r.json()
                break
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(2 ** attempt)
        else:
            raise RuntimeError(f"Inworld TTS nie odpowiedział: {last_err}")

        wa = (data.get("timestampInfo") or {}).get("wordAlignment")
        if not wa or not wa.get("words"):
            raise RuntimeError("Odpowiedź bez timestampów słów — synchronizacja niemożliwa")
        audio_path.write_bytes(base64.b64decode(data["audioContent"]))
        meta_path.write_text(json.dumps({
            "words": wa["words"],
            "starts": wa["wordStartTimeSeconds"],
            "ends": wa["wordEndTimeSeconds"],
        }, ensure_ascii=False), encoding="utf-8")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return TTSResult(audio_path, _probe_duration(audio_path), meta["words"], meta["starts"], meta["ends"])


def dry_run(text: str, cache_dir: Path, sec_per_word: float = 0.42) -> TTSResult:
    """Bez API: cisza + szacowane czasy słów. Do testów renderu i CI bez kluczy."""
    cache_dir.mkdir(parents=True, exist_ok=True)
    words = text.split()
    starts = [i * sec_per_word for i in range(len(words))]
    ends = [s + sec_per_word * 0.9 for s in starts]
    duration = len(words) * sec_per_word + 0.2
    key = hashlib.sha256(text.encode()).hexdigest()[:16]
    audio_path = cache_dir / f"dry_{key}.mp3"
    if not audio_path.exists():
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i",
                        "anullsrc=r=48000:cl=mono", "-t", f"{duration:.3f}",
                        "-c:a", "libmp3lame", "-b:a", "128k", str(audio_path)], check=True)
    return TTSResult(audio_path, _probe_duration(audio_path), words, starts, ends)


def _norm(w: str) -> str:
    return re.sub(r"[^\w]", "", w.lower())


def map_tokens_to_times(tokens: list, res: TTSResult) -> list:
    """Czas startu każdego naszego tokenu, dopasowany do słów zwróconych przez TTS.

    TTS może inaczej dzielić tekst (interpunkcja, normalizacja), więc zamiast
    liczyć indeksy robimy dopasowanie sekwencji; niedopasowane tokeny
    interpolujemy między sąsiadami.
    """
    a = [_norm(t) for t in tokens]
    b = [_norm(w) for w in res.words]
    times = [None] * len(tokens)
    for block in difflib.SequenceMatcher(a=a, b=b, autojunk=False).get_matching_blocks():
        for k in range(block.size):
            times[block.a + k] = res.starts[block.b + k]

    known = [i for i, t in enumerate(times) if t is not None]
    if not known:
        raise RuntimeError("Nie udało się dopasować słów TTS do scenariusza")
    for i in range(len(times)):
        if times[i] is None:
            prev = max((k for k in known if k < i), default=None)
            nxt = min((k for k in known if k > i), default=None)
            if prev is None:
                times[i] = times[nxt]
            elif nxt is None:
                times[i] = times[prev]
            else:
                frac = (i - prev) / (nxt - prev)
                times[i] = times[prev] + frac * (times[nxt] - times[prev])
    return times
