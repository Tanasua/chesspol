"""Wariant okładki od OpenAI: nasza okładka (cover.py) idzie do Images API (edit) z promptem właściciela,
wynik 16:9 trafia do paczki jako cover_ai.jpg i do Telegrama obok naszej — do porównania, czy model nic nie dodał.

Model: COVER_AI_MODEL (domyślnie gpt-image-2.5-sunburst — wg SDK openai 3.24 model do precyzyjnej edycji,
rozmiary WIDTHxHEIGHT podzielne przez 16), przy błędzie modelu — gpt-image-2.
Domyślnie WYŁĄCZONE (decyzja właściciela, 05.10.2026: na razie tylko nasza okładka); COVER_AI=1 włącza.
Błąd API (np. odmowa moderacji przy zdjęciach osób) nie blokuje odcinka: zwracamy None i powód.
"""
from __future__ import annotations

import base64
import io
import os
from pathlib import Path

from PIL import Image, ImageOps

PROMPT = ("Згенеруй клікбейт-кавер форматом 16:9, проаналізувавши надане мною фото, "
          "використовуючи його за основу і створи новий. "
          # dopisek właściciela (po przestawionych figurach na okładce Topalow–Anand 2010)
          "Строге правило: усі фігури і стрілки мають лишатися на тих самих клітинках, що і в прикріпленому "
          "зображенні. Стрілки можна робити яскравіші, неонові.")
MODEL = os.environ.get("COVER_AI_MODEL", "gpt-image-2.5-sunburst")
FALLBACK_MODEL = "gpt-image-2"
SIZE = "1536x864"  # 16:9, obie krawędzie podzielne przez 16
OUT_SIZE = (1280, 720)  # jak cover.jpg (YouTube)


def enabled() -> bool:
    return os.environ.get("COVER_AI", "0") == "1" and bool(os.environ.get("OPENAI_API_KEY"))


def make_ai_cover(src: Path, out: Path) -> tuple[Path | None, str]:
    """(ścieżka cover_ai.jpg | None, model albo powód błędu)."""
    if not enabled():
        return None, "вимкнено (немає OPENAI_API_KEY або COVER_AI≠1)"
    from openai import OpenAI

    client = OpenAI(timeout=300)
    errors = []
    for model in dict.fromkeys([MODEL, FALLBACK_MODEL]):
        try:
            with open(src, "rb") as fh:
                r = client.images.edit(model=model, image=("cover.jpg", fh, "image/jpeg"), prompt=PROMPT,
                                       size=SIZE, quality="high", output_format="jpeg", n=1)
        except Exception as e:  # noqa: BLE001 — wariant AI to dodatek, nie blokuje odcinka
            errors.append(f"{model}: {e.__class__.__name__}: {str(e)[:200]}")
            continue
        img = Image.open(io.BytesIO(base64.b64decode(r.data[0].b64_json))).convert("RGB")
        img = ImageOps.fit(img, OUT_SIZE, Image.LANCZOS)  # gdyby model zwrócił inny kadr
        out.parent.mkdir(parents=True, exist_ok=True)
        img.save(out, "JPEG", quality=92)
        return out, model
    return None, " | ".join(errors)


def main() -> int:
    """Jednorazowo: python src/cover_ai.py <okładka.jpg> [wyjście.jpg] — wynik do Telegrama (jeśli są sekrety)."""
    import sys

    src = Path(sys.argv[1])
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else src.with_name(src.stem + "_ai.jpg")
    path, note = make_ai_cover(src, out)
    print(f"Okładka OpenAI: {path} ({note})" if path else f"Błąd: {note}")
    if os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        import json

        from deliver import _tg

        chat = os.environ["TELEGRAM_CHAT_ID"]
        if path:
            media = [{"type": "photo", "media": "attach://ours", "caption": "🖼 Разова обкладинка: оригінал"},
                     {"type": "photo", "media": "attach://ai", "caption": f"🤖 Версія OpenAI ({note})"}]
            with open(src, "rb") as a, open(path, "rb") as b:
                _tg("sendMediaGroup", data={"chat_id": chat, "media": json.dumps(media, ensure_ascii=False)},
                    files={"ours": a, "ai": b})
            with open(path, "rb") as fh:
                _tg("sendDocument", data={"chat_id": chat, "caption": "🖼 Обкладинка OpenAI у повній якості"},
                    files={"document": (path.name, fh, "image/jpeg")})
        else:
            _tg("sendMessage", data={"chat_id": chat, "text": f"⚠️ Обкладинку OpenAI не згенеровано: {note[:600]}"})
    return 0 if path else 1


if __name__ == "__main__":
    raise SystemExit(main())
