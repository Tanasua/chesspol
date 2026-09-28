"""Stałe zwroty kanału: powitanie prowadzącego na początku odcinka i dopisek do tytułu YouTube.

Wybór zależy od numeru partii w katalogu (n): stabilny przy ponownym renderze,
a kolejne odcinki dostają kolejne warianty, więc zwroty się nie powtarzają pod rząd.

Imię prowadzącego: HOST_NAME, a gdy brak — nazwa głosu Inworld (INWORLD_VOICE_ID, np. "Wojciech"),
żeby imię zgadzało się z głosem. Bez imienia powitanie jest bez przedstawiania się.
"""
from __future__ import annotations

import hashlib
import os
import re

GREETING = [
    "Cześć, nazywam się {name}.",
    "Cześć, tu {name}.",
    "Witajcie, z tej strony {name}.",
    "Dzień dobry, nazywam się {name}.",
]
GREETING_NO_NAME = ["Cześć.", "Witajcie.", "Dzień dobry."]

INTRO = [
    "Dziś poznamy legendarną partię.",
    "Dziś pokażę Wam niezwykle ciekawą partię.",
    "Dziś poznamy partię, która na stałe weszła do historii szachów.",
    "Dziś pokażę Wam partię, którą powinien znać każdy, kto poważnie interesuje się szachami.",
    "Dziś przed nami partia, która przeszła do historii światowych szachów.",
    "Dziś pokażę Wam partię, którą każdy miłośnik szachów powinien zobaczyć przynajmniej raz.",
    "Dziś zapraszam Was na jedną z najciekawszych partii w dziejach szachów.",
    "Dziś poznamy partię, o której szachiści mówią od lat. Zaraz zobaczycie dlaczego.",
    "Dziś pokażę Wam partię, którą warto znać, nawet jeśli dopiero zaczynacie przygodę z szachami.",
    "Dziś poznamy partię, bez której trudno opowiedzieć historię szachów.",
    "Dziś pokażę Wam partię, która do dziś zachwyca szachistów na całym świecie.",
]

TITLE_HOOKS = [
    "Partia, którą musisz znać",
    "Partia, która przeszła do historii",
    "Legendarna partia",
    "Klasyka, którą warto znać",
    "Jedna z najsłynniejszych partii",
    "Partia, którą warto zobaczyć",
    "Szachowa legenda",
    "Partia na zawsze w historii szachów",
]


def _index(game: dict | None, pool: list, offset: int, salt: str) -> int:
    if game and isinstance(game.get("n"), int):
        return (game["n"] + offset) % len(pool)
    key = (game or {}).get("id", "")
    return int(hashlib.sha256(f"{salt}:{key}".encode()).hexdigest(), 16) % len(pool)


def host_name() -> str:
    name = os.environ.get("HOST_NAME", "").strip()
    if name:
        return name
    voice = os.environ.get("INWORLD_VOICE_ID", "").strip()
    return voice if re.fullmatch(r"[A-ZĄĆĘŁŃÓŚŹŻ][a-ząćęłńóśźż]+", voice) else ""


def intro_for(game: dict | None, name: str | None = None) -> str:
    name = host_name() if name is None else name
    if name:
        greet = GREETING[_index(game, GREETING, 1, "greet")].format(name=name)
    else:
        greet = GREETING_NO_NAME[_index(game, GREETING_NO_NAME, 1, "greet")]
    return f"{greet} {INTRO[_index(game, INTRO, 0, 'intro')]}"


def title_hook_for(game: dict | None) -> str:
    return TITLE_HOOKS[_index(game, TITLE_HOOKS, 3, "title")]
