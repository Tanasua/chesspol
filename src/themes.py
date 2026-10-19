"""Motywy dnia (decyzja właściciela 19.10.2026): inna plansza w każdy dzień publikacji — ta sama w filmie i na okładce,
a okładka dostaje też własną gamę kolorów (tło, akcent).

Plansze: cztery popularne schematy — brązowy (Lichess, #f0d9b5/#b58863), zielony (Chess.com, #eeeed2/#769656),
niebieski (Lichess blue, #dee3e6/#8ca2ad), fioletowy (wzorowany na motywie "purple"; odcienie dobrane przez nas).
Wybór: BOARD_THEME (nazwa) albo dzień tygodnia publikacji (scheduler/news ustawiają BOARD_THEME przed renderem).
"""
from __future__ import annotations

import os
from datetime import datetime

THEMES = {
    "brown": {"light": (240, 217, 181), "dark": (181, 136, 99),
              "cover_bg": (12, 11, 10), "accent": (214, 176, 96), "dim": (150, 140, 122)},
    "green": {"light": (238, 238, 210), "dark": (118, 150, 86),
              "cover_bg": (9, 15, 10), "accent": (156, 204, 101), "dim": (128, 150, 118)},
    "blue": {"light": (222, 227, 230), "dark": (140, 162, 173),
             "cover_bg": (8, 12, 18), "accent": (108, 186, 232), "dim": (122, 140, 156)},
    "purple": {"light": (232, 225, 241), "dark": (125, 98, 158),
               "cover_bg": (14, 9, 19), "accent": (196, 146, 240), "dim": (146, 128, 162)},
}
DAY_THEME = {1: "brown", 3: "green", 5: "blue", 6: "purple"}  # wt / czw / sob / nd (RUBRIC_DAYS)
DEFAULT = "brown"


def for_day(dt: datetime) -> str:
    """Motyw na dzień publikacji (dt w strefie kanału); dni poza grafikiem — brązowy."""
    return DAY_THEME.get(dt.weekday(), DEFAULT)


def current() -> dict:
    name = os.environ.get("BOARD_THEME", "").strip().lower()
    return THEMES.get(name, THEMES[DEFAULT])


def hex_(rgb: tuple) -> str:
    return "#%02x%02x%02x" % rgb[:3]
