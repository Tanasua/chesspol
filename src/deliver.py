"""Paczka odcinka do ręcznego uploadu: wideo, okładka, tytuł, opis, tagi, planowana data.

Paczka trafia do out/packages/<nr>-<id>/ oraz (jeśli dostępne):
  - GitHub Release (w GitHub Actions: GH_TOKEN) — trwałe, pliki do 2 GiB, widok na stronie repo;
  - Telegram (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID) — okładka z podpisem, wideo jako plik
    (Bot API: do 50 MB; większe -> link do Release), potem tytuł, opis i tagi — każde w osobnym
    bloku do skopiowania jednym dotknięciem.

Teksty dla właściciela (nagłówki, podpisy, ostrzeżenia) są po ukraińsku; to, co trafia na YouTube
(tytuł, opis, tagi) — w języku kanału.
"""
from __future__ import annotations

import html
import json
import os
import shutil
import subprocess
from pathlib import Path

import requests

TG_LIMIT = 49 * 1024 * 1024
TG_API = "https://api.telegram.org/bot{token}/{method}"
TG_CHUNK = 3500  # zapas do limitu 4096 znaków po escapowaniu HTML
CHANNEL_UK = {"pl": "польський канал", "de": "німецький канал"}


def write_package(folder: Path, video: Path, cover: Path, title: str, description: str,
                  tags: list, when_local: str) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    files = {"video": folder / "video.mp4", "cover": folder / "cover.jpg", "text": folder / "opis.txt"}
    shutil.copyfile(video, files["video"])
    shutil.copyfile(cover, files["cover"])
    text = (f"ПЛАНОВА ПУБЛІКАЦІЯ: {when_local}\n\n"
            f"ЗАГОЛОВОК:\n{title}\n\nОПИС:\n{description}\n\nТЕГИ:\n{', '.join(tags)}\n")
    files["text"].write_text(text, encoding="utf-8")
    meta = {"title": title, "description": description, "tags": tags, "publish_at_local": when_local}
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"files": files, "text": text, "title": title, "description": description, "tags": tags}


def github_release(tag: str, name: str, pkg: dict, cwd: Path) -> str | None:
    if not (os.environ.get("GITHUB_ACTIONS") and os.environ.get("GH_TOKEN")):
        return None
    notes = cwd / "out" / f"{tag}-notes.md"
    notes.write_text("```\n" + pkg["text"] + "```\n", encoding="utf-8")
    f = pkg["files"]
    # ponowny render tego samego odcinka (np. nowy głos): stary Release z tym tagiem zastępujemy
    if subprocess.run(["gh", "release", "view", tag], cwd=cwd, capture_output=True).returncode == 0:
        subprocess.run(["gh", "release", "delete", tag, "--yes", "--cleanup-tag"], cwd=cwd,
                       capture_output=True, text=True, check=True)
    r = subprocess.run(["gh", "release", "create", tag, str(f["video"]), str(f["cover"]), str(f["text"]),
                        "--title", name, "--notes-file", str(notes)],
                       cwd=cwd, capture_output=True, text=True, check=True)
    return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else None


def _tg(method: str, **kw) -> dict:
    url = TG_API.format(token=os.environ["TELEGRAM_BOT_TOKEN"], method=method)
    r = requests.post(url, timeout=300, **kw)
    r.raise_for_status()
    return r.json()


def _chunks(text: str, size: int = TG_CHUNK) -> list:
    """Dzieli tekst po wierszach na kawałki ≤ size (opis YouTube bywa dłuższy niż wiadomość Telegrama)."""
    out, cur = [], ""
    for line in text.splitlines(keepends=True):
        while len(line) > size:  # pojedynczy bardzo długi wiersz (np. zapis partii)
            if cur:
                out.append(cur)
                cur = ""
            out.append(line[:size])
            line = line[size:]
        if len(cur) + len(line) > size:
            out.append(cur)
            cur = ""
        cur += line
    if cur.strip():
        out.append(cur)
    return out


def _send_copyable(chat: str, header: str, body: str) -> None:
    """Nagłówek po ukraińsku + treść w bloku <pre> (w Telegramie: kopiowanie jednym dotknięciem)."""
    parts = _chunks(body)
    for i, part in enumerate(parts):
        head = header if len(parts) == 1 else f"{header} ({i + 1}/{len(parts)})"
        _tg("sendMessage", data={"chat_id": chat, "parse_mode": "HTML",
                                 "text": f"<b>{html.escape(head)}</b>\n<pre>{html.escape(part.strip())}</pre>"})


def telegram(pkg: dict, title: str, when_local: str, release_url: str | None, number: int | None = None) -> bool:
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (os.environ.get("TELEGRAM_BOT_TOKEN") and chat):
        return False
    from lang import L

    f = pkg["files"]
    episode = f" · випуск №{number}" if number else ""
    caption = (f"{L.flag} Новий ролик — {CHANNEL_UK.get(L.code, L.code)}{episode}\n"
               f"🗓 Опублікувати: {when_local}\n\n"
               f"Нижче: відео, потім заголовок, опис і теги окремими блоками — натисніть на блок, щоб скопіювати.")[:1024]
    with open(f["cover"], "rb") as fh:
        _tg("sendPhoto", data={"chat_id": chat, "caption": caption}, files={"photo": fh})
    if f["video"].stat().st_size <= TG_LIMIT:
        with open(f["video"], "rb") as fh:
            _tg("sendDocument", data={"chat_id": chat, "caption": "🎬 Відео для завантаження на YouTube"},
                files={"document": ("video.mp4", fh, "video/mp4")})
    else:
        _tg("sendMessage", data={"chat_id": chat,
                                 "text": f"🎬 Відео більше за 50 МБ, Telegram його не прийме — "
                                         f"завантажте тут: {release_url or 'артефакт запуску GitHub Actions'}"})
    _send_copyable(chat, "📌 Заголовок", pkg.get("title") or title)
    _send_copyable(chat, "📝 Опис", pkg.get("description") or "")
    _send_copyable(chat, "🏷 Теги (вставте в поле «Теги»)", ", ".join(pkg.get("tags") or []))
    return True
