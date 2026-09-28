"""Stałe zwroty kanału: zapowiedź na początku odcinka i dopisek do tytułu YouTube.

Wybór zależy od numeru partii w katalogu (n): stabilny przy ponownym renderze,
a kolejne odcinki dostają kolejne warianty, więc zwroty się nie powtarzają pod rząd.
"""
from __future__ import annotations

import hashlib

INTRO = [
    "Dziś pokażę Wam niezwykle ciekawą partię.",
    "Dziś pokażę Wam partię, która na stałe weszła do historii szachów.",
    "Oto partia, którą powinien znać każdy, kto poważnie interesuje się szachami.",
    "Dziś przed nami partia, która przeszła do historii światowych szachów.",
    "Pokażę Wam partię, którą każdy miłośnik szachów powinien zobaczyć przynajmniej raz.",
    "Dziś zapraszam Was na jedną z najciekawszych partii w dziejach szachów.",
    "To partia, o której szachiści mówią od lat. Zaraz zobaczycie dlaczego.",
    "Dziś pokażę Wam partię, którą warto znać, nawet jeśli dopiero zaczynacie przygodę z szachami.",
    "Przed nami partia, bez której trudno opowiedzieć historię szachów.",
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


def intro_for(game: dict | None) -> str:
    return INTRO[_index(game, INTRO, 0, "intro")]


def title_hook_for(game: dict | None) -> str:
    return TITLE_HOOKS[_index(game, TITLE_HOOKS, 3, "title")]
