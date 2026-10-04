"""Nazwy krajów (kod z countries.py) w języku kanału — podpis pod nazwiskiem w kadrze."""
from __future__ import annotations

# kod: (pl, de, en, hi)
_ROWS = """
am|Armenia|Armenien|Armenia|आर्मेनिया
ar|Argentyna|Argentinien|Argentina|अर्जेंटीना
at|Austria|Österreich|Austria|ऑस्ट्रिया
au|Australia|Australien|Australia|ऑस्ट्रेलिया
az|Azerbejdżan|Aserbaidschan|Azerbaijan|अज़रबैजान
be|Belgia|Belgien|Belgium|बेल्जियम
bg|Bułgaria|Bulgarien|Bulgaria|बुल्गारिया
br|Brazylia|Brasilien|Brazil|ब्राज़ील
by|Białoruś|Belarus|Belarus|बेलारूस
ca|Kanada|Kanada|Canada|कनाडा
ch|Szwajcaria|Schweiz|Switzerland|स्विट्ज़रलैंड
cn|Chiny|China|China|चीन
cu|Kuba|Kuba|Cuba|क्यूबा
cz|Czechy|Tschechien|Czechia|चेक गणराज्य
de|Niemcy|Deutschland|Germany|जर्मनी
dk|Dania|Dänemark|Denmark|डेनमार्क
ee|Estonia|Estland|Estonia|एस्टोनिया
es|Hiszpania|Spanien|Spain|स्पेन
fi|Finlandia|Finnland|Finland|फ़िनलैंड
fr|Francja|Frankreich|France|फ़्रांस
gb|Wielka Brytania|Großbritannien|United Kingdom|ब्रिटेन
ge|Gruzja|Georgien|Georgia|जॉर्जिया
gr|Grecja|Griechenland|Greece|ग्रीस
hr|Chorwacja|Kroatien|Croatia|क्रोएशिया
hu|Węgry|Ungarn|Hungary|हंगरी
il|Izrael|Israel|Israel|इज़राइल
in|Indie|Indien|India|भारत
ir|Iran|Iran|Iran|ईरान
is|Islandia|Island|Iceland|आइसलैंड
it|Włochy|Italien|Italy|इटली
kz|Kazachstan|Kasachstan|Kazakhstan|कज़ाख़स्तान
lv|Łotwa|Lettland|Latvia|लातविया
mx|Meksyk|Mexiko|Mexico|मेक्सिको
nl|Holandia|Niederlande|Netherlands|नीदरलैंड
no|Norwegia|Norwegen|Norway|नॉर्वे
pe|Peru|Peru|Peru|पेरू
ph|Filipiny|Philippinen|Philippines|फ़िलीपींस
pl|Polska|Polen|Poland|पोलैंड
ro|Rumunia|Rumänien|Romania|रोमानिया
rs|Serbia|Serbien|Serbia|सर्बिया
ru|Rosja|Russland|Russia|रूस
se|Szwecja|Schweden|Sweden|स्वीडन
si|Słowenia|Slowenien|Slovenia|स्लोवेनिया
sk|Słowacja|Slowakei|Slovakia|स्लोवाकिया
su|ZSRR|Sowjetunion|Soviet Union|सोवियत संघ
tr|Turcja|Türkei|Türkiye|तुर्की
ua|Ukraina|Ukraine|Ukraine|यूक्रेन
us|USA|USA|USA|अमेरिका
uz|Uzbekistan|Usbekistan|Uzbekistan|उज़्बेकिस्तान
vn|Wietnam|Vietnam|Vietnam|वियतनाम
"""
_IDX = {"pl": 1, "de": 2, "en": 3, "hi": 4}
NAMES = {r.split("|")[0]: r.split("|") for r in _ROWS.strip().splitlines()}


def country_name(code: str | None, lang: str) -> str:
    """Nazwa kraju; dla oznaczeń tekstowych bez nazwy (np. III Rzesza — tylko plakietka 'DE') i nieznanych — ''."""
    row = NAMES.get(code or "")
    return row[_IDX.get(lang, 3)] if row else ""
