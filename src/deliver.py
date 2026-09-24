"""Paczka odcinka do ręcznego uploadu: wideo, okładka, tytuł, opis, tagi, planowana data.

Paczka trafia do out/packages/<nr>-<id>/ oraz (jeśli dostępne):
  - GitHub Release (w GitHub Actions: GH_TOKEN) — trwałe, pliki do 2 GiB, widok na stronie repo;
  - Telegram (TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID) — okładka z podpisem, tekst do skopiowania,
    wideo jako plik (Bot API: do 50 MB; większe -> link do Release).
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

import requests

TG_LIMIT = 49 * 1024 * 1024
TG_API = "https://api.telegram.org/bot{token}/{method}"


def write_package(folder: Path, video: Path, cover: Path, title: str, description: str,
                  tags: list, when_local: str) -> dict:
    folder.mkdir(parents=True, exist_ok=True)
    files = {"video": folder / "video.mp4", "cover": folder / "cover.jpg", "text": folder / "opis.txt"}
    shutil.copyfile(video, files["video"])
    shutil.copyfile(cover, files["cover"])
    text = (f"PLANOWANA PUBLIKACJA: {when_local}\n\n"
            f"TYTUŁ:\n{title}\n\nOPIS:\n{description}\n\nTAGI:\n{', '.join(tags)}\n")
    files["text"].write_text(text, encoding="utf-8")
    meta = {"title": title, "description": description, "tags": tags, "publish_at_local": when_local}
    (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return {"files": files, "text": text}


def github_release(tag: str, name: str, pkg: dict, cwd: Path) -> str | None:
    if not (os.environ.get("GITHUB_ACTIONS") and os.environ.get("GH_TOKEN")):
        return None
    notes = cwd / "out" / f"{tag}-notes.md"
    notes.write_text("```\n" + pkg["text"] + "```\n", encoding="utf-8")
    f = pkg["files"]
    r = subprocess.run(["gh", "release", "create", tag, str(f["video"]), str(f["cover"]), str(f["text"]),
                        "--title", name, "--notes-file", str(notes)],
                       cwd=cwd, capture_output=True, text=True, check=True)
    return r.stdout.strip().splitlines()[-1] if r.stdout.strip() else None


def _tg(method: str, **kw) -> dict:
    url = TG_API.format(token=os.environ["TELEGRAM_BOT_TOKEN"], method=method)
    r = requests.post(url, timeout=300, **kw)
    r.raise_for_status()
    return r.json()


def telegram(pkg: dict, title: str, when_local: str, release_url: str | None) -> bool:
    chat = os.environ.get("TELEGRAM_CHAT_ID")
    if not (os.environ.get("TELEGRAM_BOT_TOKEN") and chat):
        return False
    f = pkg["files"]
    caption = f"🎬 {title}\n🗓 {when_local}"[:1024]
    with open(f["cover"], "rb") as fh:
        _tg("sendPhoto", data={"chat_id": chat, "caption": caption}, files={"photo": fh})
    if f["video"].stat().st_size <= TG_LIMIT:
        with open(f["video"], "rb") as fh:
            _tg("sendDocument", data={"chat_id": chat}, files={"document": ("video.mp4", fh, "video/mp4")})
    else:
        _tg("sendMessage", data={"chat_id": chat,
                                 "text": f"Wideo > 50 MB — pobierz z: {release_url or 'artefaktu GitHub Actions'}"})
    text = pkg["text"]
    for i in range(0, len(text), 4000):
        _tg("sendMessage", data={"chat_id": chat, "text": text[i:i + 4000]})
    return True
