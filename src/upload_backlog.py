"""Zaległe odcinki (paczki z GitHub Releases, zrobione w trybie manual i niewgrane) -> YouTube z publishAt.

Dla kanału CHANNEL bierze Release'y z prefiksem kanału (ep…/news-… dla pl, de-…, en-…, hi-…, uk-…, ru-…, tr-…),
utworzone po --after, bez testów (news-test) i bez już wgranych (state/<kanał>: pole "release" albo "video_id").
Każdy dostaje kolejny wolny termin z harmonogramu kanału (scheduler.next_slot: wt/czw/sob/nd, losowy wieczór),
wideo + tytuł/opis/tagi z opis.txt, miniatura: okładka OpenAI (cover_ai.jpg z Release albo nowa z cover.jpg), inaczej cover.jpg.
Wpis trafia do stanu kanału, więc codzienny scheduler nie zajmie tego dnia drugi raz.

  CHANNEL=pl python src/upload_backlog.py --after 2026-10-08T16:00:00Z [--dry]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import scheduler as S  # noqa: E402
from lang import L  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
WORK = ROOT / "out" / "backlog"


def _gh(*args: str) -> str:
    return subprocess.run(["gh", *args], cwd=ROOT, check=True, capture_output=True, text=True).stdout


def channel_of(tag: str) -> str:
    m = re.match(r"(de|en|hi|uk|ru|tr)-", tag)
    return m.group(1) if m else "pl"


def releases(after: str) -> list:
    raw = _gh("api", "--paginate", "repos/{owner}/{repo}/releases?per_page=100",
              "--jq", ".[] | {tag: .tag_name, created: .created_at, assets: [.assets[].name]}")
    out = [json.loads(ln) for ln in raw.splitlines() if ln.strip()]
    rel = [r for r in out if r["created"] >= after and channel_of(r["tag"]) == L.code and "news-test" not in r["tag"]
           and any(a.endswith(".mp4") for a in r["assets"])]
    return sorted(rel, key=lambda r: r["created"])


def parse_opis(text: str) -> tuple[str, str, list]:
    def section(name: str, nxt: str | None) -> str:
        part = text.split(f"{name}:\n", 1)[1]
        return (part.split(f"\n\n{nxt}:\n", 1)[0] if nxt else part).strip()
    title = section("ЗАГОЛОВОК", "ОПИС")
    desc = section("ОПИС", "ТЕГИ")
    tags = [t.strip() for t in section("ТЕГИ", None).split(",") if t.strip()]
    return title, desc, tags


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--after", required=True, help="ISO UTC: tylko Release'y utworzone później")
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()
    state = S.load_json(S.STATE, {"episodes": []})
    episodes = state["episodes"]
    done = {e.get("release") for e in episodes} | {e.get("package", "").rsplit("/", 1)[-1] for e in episodes
                                                    if e.get("video_id")}
    todo = [r for r in releases(args.after) if r["tag"] not in done]
    print(f"[{L.code}] zaległe paczki: {len(todo)}")
    now = datetime.now(timezone.utc)
    report = []
    for r in todo:
        slot, _ = S.next_slot(episodes, now, None)
        when = S.when_uk(slot)
        print(f"  {r['tag']} -> {when}")
        if args.dry:
            episodes.append({"id": r["tag"], "publish_at": slot.isoformat()})
            continue
        folder = WORK / r["tag"]
        folder.mkdir(parents=True, exist_ok=True)
        _gh("release", "download", r["tag"], "--dir", str(folder), "--clobber")
        video = next(folder.glob("*.mp4"))
        title, desc, tags = parse_opis((folder / "opis.txt").read_text(encoding="utf-8"))
        thumb = folder / "cover_ai.jpg"
        if not thumb.exists():
            from cover_ai import enabled, make_ai_cover
            if enabled():
                made, note = make_ai_cover(folder / "cover.jpg", thumb)
                print(f"    okładka OpenAI: {note}")
            thumb = thumb if thumb.exists() else folder / "cover.jpg"
        from youtube_upload import set_thumbnail, upload, video_body
        vid = upload(video, video_body(title, desc, tags, slot))
        print(f"    wgrano https://youtu.be/{vid}")
        try:
            set_thumbnail(vid, thumb)
        except Exception as e:  # noqa: BLE001
            print(f"::warning::miniatura {r['tag']}: {e.__class__.__name__}: {str(e)[:200]}")
        episodes.append({"id": r["tag"], "publish_at": slot.isoformat(), "title": title, "mode": "youtube",
                         "release": r["tag"], "video_id": vid, "thumbnail": thumb.name, "rubric": "backlog"})
        S.save_json(S.STATE, state)  # po każdym uploadzie — bez podwójnego wgrania przy błędzie
        report.append(f"{when}\n{title}\nhttps://youtu.be/{vid}")
    if report and os.environ.get("TELEGRAM_BOT_TOKEN") and os.environ.get("TELEGRAM_CHAT_ID"):
        from deliver import _tg
        _tg("sendMessage", data={"chat_id": os.environ["TELEGRAM_CHAT_ID"],
                                 "text": f"{L.flag} Завантажено на YouTube і заплановано ({len(report)}):\n\n"
                                         + "\n\n".join(report)})
    return 0


if __name__ == "__main__":
    sys.exit(main())
