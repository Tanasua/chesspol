"""Kanał i język odcinka: CHANNEL=pl (domyślnie) albo CHANNEL=de.

Wspólne dla kanałów: katalog 100 partii, PGN, zdjęcia, render, muzyka, Telegram.
Osobne: kolejność publikacji (pole n / n_de w katalogu), scenariusze, stan harmonogramu,
zapis ruchów dla lektora, prompt, stałe zwroty, teksty opisu YouTube i silnik TTS.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Channel:
    code: str
    tts: str                 # "inworld" | "elevenlabs"
    voice_env: str           # zmienna środowiska z identyfikatorem głosu
    order_key: str           # pole kolejności w catalog/games.json
    suffix: str              # sufiks pól językowych w katalogu (white_pl, label_de, …)
    state: Path
    scripts: Path
    out: Path
    tag_prefix: str          # GitHub Release: <prefix>ep001-<id>
    flag: str                # znacznik w Telegramie
    prompt: Path
    t: dict = field(default_factory=dict)


PL = Channel(
    code="pl", tts="inworld", voice_env="INWORLD_VOICE_ID", order_key="n", suffix="_pl",
    state=ROOT / "state" / "schedule.json", scripts=ROOT / "scripts", out=ROOT / "out",
    tag_prefix="", flag="🇵🇱", prompt=ROOT / "prompts" / "script_system_pl.md",
    t={
        "white": "Białe", "black": "Czarne", "year": "Rok", "event": "Wydarzenie", "place": "Miejsce",
        "round": "Runda/partia", "result": "Wynik", "nickname": "Znana nazwa partii", "notes": "Uwagi",
        "white_side": "białe", "black_side": "czarne",
        "table_head": "N | ruch | kolor | SAN | FEN przed ruchem | ocena po ruchu (+ = lepiej dla białych)",
        "engine_best": "najlepsza odpowiedź wg silnika", "none": "brak", "mate": "mat", "over": "koniec",
        "pgn_headers": "NAGŁÓWKI PGN", "plies": "PÓŁRUCHY (łącznie {n})", "facts": "FAKTY (zweryfikowane)",
        "catalog_facts": "FAKTY Z KATALOGU (zweryfikowane)",
        "no_facts": "FAKTY: brak — używaj wyłącznie nagłówków PGN.",
        "no_engine": "OCENY SILNIKA: brak — nie używaj ocen typu \"błąd\", \"najlepszy ruch\".",
        "write": "Napisz scenariusz odcinka zgodnie z zasadami. Zwróć wyłącznie JSON.",
        "fix": "Walidacja odrzuciła scenariusz:\n{err}\n\nPopraw i zwróć cały scenariusz ponownie, wyłącznie JSON.",
        "chapters": "Rozdziały:", "pgn": "Zapis partii (PGN):", "photos": "Zdjęcia (Wikimedia Commons):",
        "res_mate": "Mat", "res_draw": "Remis",
        "res_resign": {"white": "Białe poddały się", "black": "Czarne poddały się"},
        "res_time": {"white": "Białe przegrały na czas", "black": "Czarne przegrały na czas"},
        "unknown_author": "autor nieznany", "photo_by": "fot.", "moves_header": "RUCHY",
        "verified": "Zapis partii sprawdzony w co najmniej dwóch bazach partii. ",
        "hashtags": "#szachy #chess #historiaszachów",
        "tags": ["szachy", "chess", "partia szachowa", "historia szachów", "słynne partie szachowe"],
        "year_tag": "szachy {year}",
    },
)

DE = Channel(
    code="de", tts="elevenlabs", voice_env="ELEVENLABS_VOICE_ID", order_key="n_de", suffix="_de",
    state=ROOT / "state" / "schedule_de.json", scripts=ROOT / "scripts_de", out=ROOT / "out" / "de",
    tag_prefix="de-", flag="🇩🇪", prompt=ROOT / "prompts" / "script_system_de.md",
    t={
        "white": "Weiß", "black": "Schwarz", "year": "Jahr", "event": "Veranstaltung", "place": "Ort",
        "round": "Runde/Partie", "result": "Ergebnis", "nickname": "Bekannter Name der Partie", "notes": "Hinweise",
        "white_side": "Weiß", "black_side": "Schwarz",
        "table_head": "N | Zug | Farbe | SAN | FEN vor dem Zug | Bewertung nach dem Zug (+ = besser für Weiß)",
        "engine_best": "beste Antwort laut Engine", "none": "keine", "mate": "matt", "over": "Ende",
        "pgn_headers": "PGN-KOPFZEILEN", "plies": "HALBZÜGE (insgesamt {n})", "facts": "FAKTEN (geprüft)",
        "catalog_facts": "FAKTEN AUS DEM KATALOG (geprüft)",
        "no_facts": "FAKTEN: keine — verwende ausschließlich die PGN-Kopfzeilen.",
        "no_engine": "ENGINE-BEWERTUNGEN: keine — keine Urteile wie \"Fehler\" oder \"bester Zug\".",
        "write": "Schreibe das Skript der Folge nach den Regeln. Gib ausschließlich JSON zurück.",
        "fix": "Die Validierung hat das Skript abgelehnt (Meldung auf Polnisch):\n{err}\n\n"
               "Korrigiere es und gib das ganze Skript erneut zurück, ausschließlich JSON.",
        "chapters": "Kapitel:", "pgn": "Partienotation (PGN):", "photos": "Fotos (Wikimedia Commons):",
        "res_mate": "Matt", "res_draw": "Remis",
        "res_resign": {"white": "Weiß gibt auf", "black": "Schwarz gibt auf"},
        "res_time": {"white": "Weiß verliert auf Zeit", "black": "Schwarz verliert auf Zeit"},
        "unknown_author": "Autor unbekannt", "photo_by": "Foto:", "moves_header": "ZÜGE",
        "verified": "Die Partienotation wurde in mindestens zwei Partiedatenbanken überprüft. ",
        "hashtags": "#schach #chess #schachgeschichte",
        "tags": ["Schach", "chess", "Schachpartie", "Schachgeschichte", "berühmte Schachpartien"],
        "year_tag": "Schach {year}",
    },
)

CHANNELS = {"pl": PL, "de": DE}
L = CHANNELS[os.environ.get("CHANNEL", "pl").strip().lower() or "pl"]


def field_(entry: dict | None, name: str):
    """Pole katalogu w wersji językowej kanału (np. label_de), w razie braku — wersja bazowa."""
    e = entry or {}
    v = e.get(f"{name}{L.suffix}")
    return v if v not in (None, "") else e.get(name)


def moves_word(n: int) -> str:
    if L.code == "de":
        return "Zug" if n == 1 else "Züge"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "ruchy"
    return "ruch" if n == 1 else "ruchów"


def result_label(game, ending: str | None = None) -> tuple[str, str]:
    """('0–1', 'Białe poddały się') — plansza wyniku na końcu odcinka.
    Partia rozstrzygnięta bez mata na szachownicy = poddanie; wyjątki w katalogu: ending="time"."""
    result = game.headers.get("Result", "*")
    score = {"1-0": "1–0", "0-1": "0–1", "1/2-1/2": "½–½"}.get(result, "")
    if not score:
        return "", ""
    if result == "1/2-1/2":
        return score, L.t["res_draw"]
    if game.plies and game.plies[-1].is_mate:
        return score, L.t["res_mate"]
    loser = "black" if result == "1-0" else "white"
    return score, L.t["res_time" if ending == "time" else "res_resign"][loser]


def credit_author(author: str | None) -> str:
    """Autor zdjęcia do podpisu; polskie dopiski z fetch_portraits.py tłumaczone na język kanału."""
    a = author or L.t["unknown_author"]
    if L.code != "pl":
        a = a.replace("autor nieznany", L.t["unknown_author"]).replace("; oprac.", "; bearb.")
    return a


def notation():
    """Moduł zapisu ruchów kanału: spoken(ply), san_local(san), label(ply), PREPOSITIONS."""
    if L.code == "de":
        import de_notation as mod
    else:
        import pl_notation as mod
    return mod
