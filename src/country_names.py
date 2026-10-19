"""Nazwy krajów (kod z countries.py) w języku kanału — podpis pod nazwiskiem w kadrze."""
from __future__ import annotations

# kod: (pl, de, en, hi, uk, ru, tr)
_ROWS = """
am|Armenia|Armenien|Armenia|आर्मेनिया|Вірменія|Армения|Ermenistan
ar|Argentyna|Argentinien|Argentina|अर्जेंटीना|Аргентина|Аргентина|Arjantin
at|Austria|Österreich|Austria|ऑस्ट्रिया|Австрія|Австрия|Avusturya
au|Australia|Australien|Australia|ऑस्ट्रेलिया|Австралія|Австралия|Avustralya
az|Azerbejdżan|Aserbaidschan|Azerbaijan|अज़रबैजान|Азербайджан|Азербайджан|Azerbaycan
be|Belgia|Belgien|Belgium|बेल्जियम|Бельгія|Бельгия|Belçika
bg|Bułgaria|Bulgarien|Bulgaria|बुल्गारिया|Болгарія|Болгария|Bulgaristan
br|Brazylia|Brasilien|Brazil|ब्राज़ील|Бразилія|Бразилия|Brezilya
by|Białoruś|Belarus|Belarus|बेलारूस|Білорусь|Беларусь|Belarus
ca|Kanada|Kanada|Canada|कनाडा|Канада|Канада|Kanada
ch|Szwajcaria|Schweiz|Switzerland|स्विट्ज़रलैंड|Швейцарія|Швейцария|İsviçre
cn|Chiny|China|China|चीन|Китай|Китай|Çin
cu|Kuba|Kuba|Cuba|क्यूबा|Куба|Куба|Küba
cz|Czechy|Tschechien|Czechia|चेक गणराज्य|Чехія|Чехия|Çekya
de|Niemcy|Deutschland|Germany|जर्मनी|Німеччина|Германия|Almanya
dk|Dania|Dänemark|Denmark|डेनमार्क|Данія|Дания|Danimarka
ee|Estonia|Estland|Estonia|एस्टोनिया|Естонія|Эстония|Estonya
es|Hiszpania|Spanien|Spain|स्पेन|Іспанія|Испания|İspanya
fi|Finlandia|Finnland|Finland|फ़िनलैंड|Фінляндія|Финляндия|Finlandiya
fr|Francja|Frankreich|France|फ़्रांस|Франція|Франция|Fransa
gb|Wielka Brytania|Großbritannien|United Kingdom|ब्रिटेन|Велика Британія|Великобритания|Birleşik Krallık
ge|Gruzja|Georgien|Georgia|जॉर्जिया|Грузія|Грузия|Gürcistan
gr|Grecja|Griechenland|Greece|ग्रीस|Греція|Греция|Yunanistan
hr|Chorwacja|Kroatien|Croatia|क्रोएशिया|Хорватія|Хорватия|Hırvatistan
hu|Węgry|Ungarn|Hungary|हंगरी|Угорщина|Венгрия|Macaristan
il|Izrael|Israel|Israel|इज़राइल|Ізраїль|Израиль|İsrail
in|Indie|Indien|India|भारत|Індія|Индия|Hindistan
ir|Iran|Iran|Iran|ईरान|Іран|Иран|İran
is|Islandia|Island|Iceland|आइसलैंड|Ісландія|Исландия|İzlanda
it|Włochy|Italien|Italy|इटली|Італія|Италия|İtalya
kz|Kazachstan|Kasachstan|Kazakhstan|कज़ाख़स्तान|Казахстан|Казахстан|Kazakistan
lv|Łotwa|Lettland|Latvia|लातविया|Латвія|Латвия|Letonya
mx|Meksyk|Mexiko|Mexico|मेक्सिको|Мексика|Мексика|Meksika
nl|Holandia|Niederlande|Netherlands|नीदरलैंड|Нідерланди|Нидерланды|Hollanda
no|Norwegia|Norwegen|Norway|नॉर्वे|Норвегія|Норвегия|Norveç
pe|Peru|Peru|Peru|पेरू|Перу|Перу|Peru
ph|Filipiny|Philippinen|Philippines|फ़िलीपींस|Філіппіни|Филиппины|Filipinler
pl|Polska|Polen|Poland|पोलैंड|Польща|Польша|Polonya
ro|Rumunia|Rumänien|Romania|रोमानिया|Румунія|Румыния|Romanya
rs|Serbia|Serbien|Serbia|सर्बिया|Сербія|Сербия|Sırbistan
ru|Rosja|Russland|Russia|रूस|Росія|Россия|Rusya
se|Szwecja|Schweden|Sweden|स्वीडन|Швеція|Швеция|İsveç
si|Słowenia|Slowenien|Slovenia|स्लोवेनिया|Словенія|Словения|Slovenya
sk|Słowacja|Slowakei|Slovakia|स्लोवाकिया|Словаччина|Словакия|Slovakya
su|ZSRR|Sowjetunion|Soviet Union|सोवियत संघ|СРСР|СССР|Sovyetler Birliği
tr|Turcja|Türkei|Türkiye|तुर्की|Туреччина|Турция|Türkiye
ua|Ukraina|Ukraine|Ukraine|यूक्रेन|Україна|Украина|Ukrayna
us|USA|USA|USA|अमेरिका|США|США|ABD
uz|Uzbekistan|Usbekistan|Uzbekistan|उज़्बेकिस्तान|Узбекистан|Узбекистан|Özbekistan
vn|Wietnam|Vietnam|Vietnam|वियतनाम|В'єтнам|Вьетнам|Vietnam
"""
_IDX = {"pl": 1, "de": 2, "en": 3, "hi": 4, "uk": 5, "ru": 6, "tr": 7}
NAMES = {r.split("|")[0]: r.split("|") for r in _ROWS.strip().splitlines()}


def country_name(code: str | None, lang: str) -> str:
    """Nazwa kraju; dla oznaczeń tekstowych bez nazwy (np. III Rzesza — tylko plakietka 'DE') i nieznanych — ''."""
    row = NAMES.get(code or "")
    return row[_IDX.get(lang, 3)] if row else ""
