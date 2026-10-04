"""Kanał i język odcinka: CHANNEL=pl (domyślnie), de, en (angielski, odbiorca amerykański) albo hi (hindi, Indie).

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
    country: str = ""        # kod ISO kraju kanału ("swój" gracz w nowościach); domyślnie = code
    fallback: str = ""       # sufiks pól katalogu, gdy brak wersji kanału (hi -> _en); pusty = pole bazowe
    font: str = "Montserrat"  # krój w kadrze i na okładce (hi: Hind — dewanagari + łacinka, SIL OFL)


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
        "unknown_author": "autor nieznany", "photo_by": "fot.", "moves_header": "RUCHY",
        "verified": "Zapis partii sprawdzony w co najmniej dwóch bazach partii. ",
        "hashtags": "#szachy #chess #historiaszachów",
        "tags": ["szachy", "chess", "partia szachowa", "historia szachów", "słynne partie szachowe"],
        "year_tag": "szachy {year}",
        "stage": {1: "Finał", 2: "Półfinał", 4: "Ćwierćfinał", 8: "1/8 finału", 16: "1/16 finału"},
        "third": "Mecz o 3. miejsce", "this_game": "TA PARTIA", "standings": "Tabela przed tą partią",
        "round_n": "Runda {n}", "pts": "pkt", "news_tags": ["szachy na żywo", "turniej szachowy", "wiadomości szachowe"],
        "news_hashtags": "#szachy #chess #turniejszachowy",
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
        "unknown_author": "Autor unbekannt", "photo_by": "Foto:", "moves_header": "ZÜGE",
        "verified": "Die Partienotation wurde in mindestens zwei Partiedatenbanken überprüft. ",
        "hashtags": "#schach #chess #schachgeschichte",
        "tags": ["Schach", "chess", "Schachpartie", "Schachgeschichte", "berühmte Schachpartien"],
        "year_tag": "Schach {year}",
        "stage": {1: "Finale", 2: "Halbfinale", 4: "Viertelfinale", 8: "Achtelfinale", 16: "Sechzehntelfinale"},
        "third": "Spiel um Platz 3", "this_game": "DIESE PARTIE", "standings": "Tabelle vor dieser Partie",
        "round_n": "Runde {n}", "pts": "Pkt.", "news_tags": ["Schach live", "Schachturnier", "Schachnachrichten"],
        "news_hashtags": "#schach #chess #schachturnier",
    },
)

EN = Channel(
    code="en", tts="elevenlabs", voice_env="ELEVENLABS_VOICE_ID", order_key="n_en", suffix="_en",
    state=ROOT / "state" / "schedule_en.json", scripts=ROOT / "scripts_en", out=ROOT / "out" / "en",
    tag_prefix="en-", flag="🇺🇸", prompt=ROOT / "prompts" / "script_system_en.md", country="us",
    t={
        "white": "White", "black": "Black", "year": "Year", "event": "Event", "place": "Location",
        "round": "Round/game", "result": "Result", "nickname": "Known as", "notes": "Notes",
        "white_side": "White", "black_side": "Black",
        "table_head": "N | move | color | SAN | FEN before the move | eval after the move (+ = better for White)",
        "engine_best": "engine's best reply", "none": "none", "mate": "mate", "over": "game over",
        "pgn_headers": "PGN HEADERS", "plies": "HALF-MOVES ({n} total)", "facts": "FACTS (verified)",
        "catalog_facts": "FACTS FROM THE CATALOG (verified)",
        "no_facts": "FACTS: none — use only the PGN headers.",
        "no_engine": "ENGINE EVALUATIONS: none — no verdicts like \"mistake\" or \"best move\".",
        "write": "Write the episode script following the rules. Return JSON only.",
        "fix": "Validation rejected the script (message in Polish):\n{err}\n\n"
               "Fix it and return the whole script again, JSON only.",
        "chapters": "Chapters:", "pgn": "Game score (PGN):", "photos": "Photos (Wikimedia Commons):",
        "unknown_author": "unknown author", "photo_by": "Photo:", "moves_header": "MOVES",
        "verified": "The game score was checked against at least two game databases. ",
        "hashtags": "#chess #chesshistory #famouschessgames",
        "tags": ["chess", "chess game", "chess history", "famous chess games", "classic chess games"],
        "year_tag": "chess {year}",
        "stage": {1: "Final", 2: "Semifinal", 4: "Quarterfinal", 8: "Round of 16", 16: "Round of 32"},
        "third": "Third-place match", "this_game": "THIS GAME", "standings": "Standings before this game",
        "round_n": "Round {n}", "pts": "pts", "news_tags": ["chess news", "chess tournament", "live chess"],
        "news_hashtags": "#chess #chessnews #chesstournament",
    },
)

HI = Channel(
    code="hi", tts="elevenlabs", voice_env="ELEVENLABS_VOICE_ID", order_key="n_hi", suffix="_hi",
    state=ROOT / "state" / "schedule_hi.json", scripts=ROOT / "scripts_hi", out=ROOT / "out" / "hi",
    tag_prefix="hi-", flag="🇮🇳", prompt=ROOT / "prompts" / "script_system_hi.md", country="in",
    fallback="_en", font="Hind",
    # teksty dla LLM po angielsku; teksty dla widza w hindi — NIE zweryfikowane przez native speakera
    t={
        "white": "सफ़ेद", "black": "काला", "year": "वर्ष", "event": "प्रतियोगिता", "place": "स्थान",
        "round": "राउंड/बाज़ी", "result": "परिणाम", "nickname": "प्रसिद्ध नाम", "notes": "टिप्पणी",
        "white_side": "White", "black_side": "Black",
        "table_head": "N | move | color | SAN | FEN before the move | eval after the move (+ = better for White)",
        "engine_best": "engine's best reply", "none": "none", "mate": "mate", "over": "game over",
        "pgn_headers": "PGN HEADERS", "plies": "HALF-MOVES ({n} total)", "facts": "FACTS (verified)",
        "catalog_facts": "FACTS FROM THE CATALOG (verified)",
        "no_facts": "FACTS: none — use only the PGN headers.",
        "no_engine": "ENGINE EVALUATIONS: none — no verdicts like \"mistake\" or \"best move\".",
        "write": "Write the episode script following the rules (narration in Hindi). Return JSON only.",
        "fix": "Validation rejected the script (message in Polish):\n{err}\n\n"
               "Fix it and return the whole script again, JSON only.",
        "chapters": "अध्याय:", "pgn": "बाज़ी का रिकॉर्ड (PGN):", "photos": "तस्वीरें (Wikimedia Commons):",
        "unknown_author": "अज्ञात लेखक", "photo_by": "फ़ोटो:", "moves_header": "चालें",
        "verified": "बाज़ी का रिकॉर्ड कम से कम दो शतरंज डेटाबेस में जाँचा गया है। ",
        "hashtags": "#शतरंज #chess #chesshindi",
        "tags": ["शतरंज", "chess", "chess hindi", "शतरंज का इतिहास", "famous chess games"],
        "year_tag": "शतरंज {year}",
        "stage": {1: "फ़ाइनल", 2: "सेमीफ़ाइनल", 4: "क्वार्टरफ़ाइनल", 8: "राउंड ऑफ़ 16", 16: "राउंड ऑफ़ 32"},
        "third": "तीसरे स्थान का मुक़ाबला", "this_game": "यह बाज़ी", "standings": "इस बाज़ी से पहले की तालिका",
        "round_n": "राउंड {n}", "pts": "अंक", "news_tags": ["शतरंज समाचार", "chess news", "chess tournament"],
        "news_hashtags": "#शतरंज #chess #chessnews",
    },
)

CHANNELS = {"pl": PL, "de": DE, "en": EN, "hi": HI}
L = CHANNELS[os.environ.get("CHANNEL", "pl").strip().lower() or "pl"]


NATIONAL = ROOT / "catalog" / f"national_{L.country or L.code}.json"  # rubryka "swoi" mistrzowie kraju kanału


def field_(entry: dict | None, name: str):
    """Pole katalogu w wersji językowej kanału (np. label_de), w razie braku — wersja bazowa."""
    e = entry or {}
    for key in (f"{name}{L.suffix}", f"{name}{L.fallback}" if L.fallback else None):
        if key and e.get(key) not in (None, ""):
            return e[key]
    return e.get(name)


def moves_word(n: int) -> str:
    if L.code == "hi":
        return "चाल" if n == 1 else "चालें"
    if L.code == "en":
        return "move" if n == 1 else "moves"
    if L.code == "de":
        return "Zug" if n == 1 else "Züge"
    if n % 10 in (2, 3, 4) and n % 100 not in (12, 13, 14):
        return "ruchy"
    return "ruch" if n == 1 else "ruchów"


def credit_author(author: str | None) -> str:
    """Autor zdjęcia do podpisu; polskie dopiski z fetch_portraits.py tłumaczone na język kanału."""
    a = author or L.t["unknown_author"]
    if L.code != "pl":
        a = a.replace("autor nieznany", L.t["unknown_author"]).replace(
            "; oprac.", {"de": "; bearb.", "hi": "; संपादन"}.get(L.code, "; edited by"))
    return a


def notation():
    """Moduł zapisu ruchów kanału: spoken(ply), san_local(san), label(ply), PREPOSITIONS."""
    if L.code == "de":
        import de_notation as mod
    elif L.code == "en":
        import en_notation as mod
    elif L.code == "hi":
        import hi_notation as mod
    else:
        import pl_notation as mod
    return mod
