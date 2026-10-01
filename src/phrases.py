"""Stałe zwroty kanału: powitanie prowadzącego, zakończenie i dopisek do tytułu YouTube.

Teksty w języku kanału (CHANNEL, src/lang.py). Wybór wariantu zależy od pozycji partii
w kolejności kanału (n / n_de): stabilny przy ponownym renderze, a kolejne odcinki dostają
kolejne warianty, więc zwroty się nie powtarzają pod rząd.

Imię prowadzącego: HOST_NAME, a gdy brak — nazwa głosu (np. "Wojciech" w Inworld), żeby imię
zgadzało się z głosem. Głosy ElevenLabs mają losowe identyfikatory — tam imię tylko z HOST_NAME.
Bez imienia powitanie jest bez przedstawiania się.
"""
from __future__ import annotations

import hashlib
import os
import re

from lang import L

TEXTS = {
    "pl": {
        "greeting": [
            "Cześć, nazywam się {name}.",
            "Cześć, tu {name}.",
            "Witajcie, z tej strony {name}.",
            "Dzień dobry, nazywam się {name}.",
        ],
        "greeting_no_name": ["Cześć.", "Witajcie.", "Dzień dobry."],
        "intro": [
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
        ],
        "outro": ("Dziękujemy za obejrzenie. Jeśli interesujecie się szachami, "
                  "polubcie ten film i zasubskrybujcie kanał."),
        "title_hooks": [
            "Partia, którą musisz znać",
            "Partia, która przeszła do historii",
            "Legendarna partia",
            "Klasyka, którą warto znać",
            "Jedna z najsłynniejszych partii",
            "Partia, którą warto zobaczyć",
            "Szachowa legenda",
            "Partia na zawsze w historii szachów",
        ],
    },
    "de": {
        "greeting": [
            "Hallo, ich bin {name}.",
            "Hallo und willkommen, hier ist {name}.",
            "Guten Tag, mein Name ist {name}.",
            "Willkommen, ich bin {name}.",
        ],
        "greeting_no_name": ["Hallo.", "Willkommen.", "Guten Tag."],
        "intro": [
            "Heute zeige ich euch eine legendäre Partie.",
            "Heute zeige ich euch eine unglaublich spannende Partie.",
            "Heute sehen wir uns eine Partie an, die in die Schachgeschichte eingegangen ist.",
            "Heute zeige ich euch eine Partie, die jeder kennen sollte, der sich ernsthaft für Schach interessiert.",
            "Heute geht es um eine Partie, die Schachgeschichte geschrieben hat.",
            "Heute zeige ich euch eine Partie, die jeder Schachfan mindestens einmal gesehen haben sollte.",
            "Heute nehme ich euch mit zu einer der spannendsten Partien der Schachgeschichte.",
            "Heute sehen wir uns eine Partie an, über die Schachspieler seit Jahrzehnten sprechen. Gleich seht ihr, warum.",
            "Heute zeige ich euch eine Partie, die ihr kennen solltet, auch wenn ihr gerade erst mit dem Schach anfangt.",
            "Heute geht es um eine Partie, ohne die man die Geschichte des Schachs kaum erzählen kann.",
            "Heute zeige ich euch eine Partie, die Schachspieler auf der ganzen Welt bis heute begeistert.",
        ],
        "outro": ("Danke fürs Zuschauen. Wenn ihr euch für Schach interessiert, "
                  "gebt diesem Video ein Like und abonniert den Kanal."),
        "title_hooks": [
            "Diese Partie musst du kennen",
            "Eine Partie für die Geschichtsbücher",
            "Legendäre Partie",
            "Ein Klassiker, den man kennen sollte",
            "Eine der berühmtesten Partien",
            "Diese Partie solltest du sehen",
            "Eine Schachlegende",
            "Für immer in der Schachgeschichte",
        ],
    },
}
T = TEXTS[L.code]
GREETING, GREETING_NO_NAME, INTRO, TITLE_HOOKS = T["greeting"], T["greeting_no_name"], T["intro"], T["title_hooks"]
OUTRO = T["outro"]


def _index(game: dict | None, pool: list, offset: int, salt: str) -> int:
    if game and isinstance(game.get(L.order_key), int):
        return (game[L.order_key] + offset) % len(pool)
    key = (game or {}).get("id", "")
    return int(hashlib.sha256(f"{salt}:{key}".encode()).hexdigest(), 16) % len(pool)


def host_name() -> str:
    name = os.environ.get("HOST_NAME", "").strip()
    if name:
        return name
    voice = os.environ.get(L.voice_env, "").strip()
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
