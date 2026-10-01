"""Klient ElevenLabs TTS (POST /v1/text-to-speech/{voice_id}/with-timestamps) z cache na dysku.

API zwraca czasy znaków (alignment); składamy z nich czasy słów w tym samym formacie
co tts_inworld.TTSResult, więc reszta potoku (dopasowanie markerów, render) jest wspólna.

Zmienne: ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID, ELEVENLABS_MODEL (domyślnie eleven_multilingual_v2).
NIE zweryfikowane na prawdziwym kluczu w środowisku deweloperskim — format odpowiedzi według dokumentacji.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import time
from pathlib import Path

import requests

from tts_inworld import TTSRequestError, TTSResult, _probe_duration

API_URL = "https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/with-timestamps"
DEFAULT_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
OUTPUT_FORMAT = "mp3_44100_128"


def words_from_alignment(alignment: dict) -> tuple[list, list, list]:
    """Znaki z czasami -> (słowa, starty, końce). Słowo = ciąg znaków bez białych znaków."""
    chars = alignment.get("characters") or []
    starts = alignment.get("character_start_times_seconds") or []
    ends = alignment.get("character_end_times_seconds") or []
    words, ws, we = [], [], []
    cur, cur_s, cur_e = "", None, None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if cur:
                words.append(cur), ws.append(cur_s), we.append(cur_e)
            cur, cur_s = "", None
            continue
        if not cur:
            cur_s = s
        cur += ch
        cur_e = e
    if cur:
        words.append(cur), ws.append(cur_s), we.append(cur_e)
    return words, ws, we


def synthesize(text: str, cache_dir: Path, voice_id: str, model: str = DEFAULT_MODEL,
               retries: int = 3) -> TTSResult:
    api_key = os.environ.get("ELEVENLABS_API_KEY")
    if not api_key:
        raise RuntimeError("Brak ELEVENLABS_API_KEY")

    cache_dir.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(json.dumps(["elevenlabs", text, voice_id, model]).encode()).hexdigest()[:16]
    audio_path = cache_dir / f"el_{key}.mp3"
    meta_path = cache_dir / f"el_{key}.json"

    if not (audio_path.exists() and meta_path.exists()):
        body = {"text": text, "model_id": model}
        headers = {"xi-api-key": api_key, "Content-Type": "application/json"}
        url = API_URL.format(voice_id=voice_id)
        last_err = None
        for attempt in range(retries):
            try:
                r = requests.post(url, params={"output_format": OUTPUT_FORMAT}, json=body,
                                  headers=headers, timeout=180)
                if r.status_code == 429 or r.status_code >= 500:
                    raise RuntimeError(f"HTTP {r.status_code}: {r.text[:300]}")
                if r.status_code >= 400:  # zły klucz, głos, brak środków — ponawianie nic nie da
                    raise TTSRequestError(f"HTTP {r.status_code}: {r.text[:500]} (voice_id={voice_id!r}, model={model!r})")
                data = r.json()
                break
            except TTSRequestError:
                raise
            except Exception as e:  # noqa: BLE001
                last_err = e
                time.sleep(2 ** (attempt + 1))
        else:
            raise RuntimeError(f"ElevenLabs TTS nie odpowiedział: {last_err}")

        words, starts, ends = words_from_alignment(data.get("alignment") or {})
        if not words:
            raise RuntimeError("Odpowiedź ElevenLabs bez alignment — synchronizacja niemożliwa")
        audio_path.write_bytes(base64.b64decode(data["audio_base64"]))
        meta_path.write_text(json.dumps({"words": words, "starts": starts, "ends": ends},
                                        ensure_ascii=False), encoding="utf-8")

    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    return TTSResult(audio_path, _probe_duration(audio_path), meta["words"], meta["starts"], meta["ends"])
