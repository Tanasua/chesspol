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
    "en": {
        "greeting": [
            "Hi, I'm {name}.",
            "Hey everyone, {name} here.",
            "Hello and welcome, I'm {name}.",
            "Welcome back, it's {name}.",
        ],
        "greeting_no_name": ["Hi everyone.", "Hello and welcome.", "Welcome back."],
        "intro": [
            "Today we're looking at a legendary game.",
            "Today I'm going to show you an incredibly exciting game.",
            "Today we're diving into a game that made chess history.",
            "Today I'm showing you a game every serious chess fan should know.",
            "Today we're going through a game that changed the history of chess.",
            "Today I'm going to show you a game every chess lover should see at least once.",
            "Today I'm taking you through one of the most exciting games in chess history.",
            "Today we're looking at a game chess players have been talking about for decades. You'll see why in a moment.",
            "Today I'm showing you a game worth knowing, even if you're just getting started with chess.",
            "Today we're looking at a game you can't leave out of the story of chess.",
            "Today I'm going to show you a game that still amazes chess players around the world.",
        ],
        "outro": ("Thanks for watching. If you're into chess, hit the like button "
                  "and subscribe to the channel."),
        "title_hooks": [
            "A Game You Need to Know",
            "A Game That Made History",
            "Legendary Game",
            "A Classic Worth Knowing",
            "One of the Most Famous Games Ever",
            "A Game You Have to See",
            "A Chess Legend",
            "Forever in Chess History",
        ],
    },
    # hindi: forma "हम" (my) — bez rodzaju gramatycznego lektora; NIE zweryfikowane przez native speakera
    "hi": {
        "greeting": ["नमस्ते, मैं {name} हूँ।", "नमस्कार दोस्तों, मैं {name}।", "स्वागत है, मैं {name} हूँ।"],
        "greeting_no_name": ["नमस्ते।", "नमस्कार दोस्तों।", "स्वागत है।"],
        "intro": [
            "आज हम एक ऐतिहासिक बाज़ी देखेंगे।",
            "आज हम एक बेहद रोमांचक बाज़ी देखेंगे।",
            "आज हम वह बाज़ी देखेंगे, जो शतरंज के इतिहास में दर्ज हो गई।",
            "आज हम वह बाज़ी देखेंगे, जिसे हर गंभीर शतरंज प्रेमी को जानना चाहिए।",
            "आज हम एक ऐसी बाज़ी देखेंगे, जिसने शतरंज के इतिहास में अपनी जगह बनाई।",
            "आज हम वह बाज़ी देखेंगे, जिसे हर शतरंज प्रेमी को कम से कम एक बार ज़रूर देखना चाहिए।",
            "आज हम शतरंज के इतिहास की सबसे रोमांचक बाज़ियों में से एक देखेंगे।",
            "आज हम वह बाज़ी देखेंगे, जिसके बारे में शतरंज खिलाड़ी आज भी बात करते हैं। अभी समझ आएगा क्यों।",
            "आज की बाज़ी जानने लायक है, चाहे आपने शतरंज अभी-अभी सीखना शुरू किया हो।",
            "आज हम वह बाज़ी देखेंगे, जिसके बिना शतरंज की कहानी अधूरी है।",
            "आज हम वह बाज़ी देखेंगे, जो दुनिया भर के शतरंज खिलाड़ियों को आज भी हैरान करती है।",
        ],
        "outro": "देखने के लिए धन्यवाद। अगर आपको शतरंज पसंद है, तो इस वीडियो को लाइक करें और चैनल को सब्सक्राइब करें।",
        "title_hooks": [
            "यह बाज़ी ज़रूर जानिए", "इतिहास रचने वाली बाज़ी", "ऐतिहासिक बाज़ी", "जानने लायक क्लासिक",
            "सबसे मशहूर बाज़ियों में से एक", "यह बाज़ी ज़रूर देखिए", "शतरंज की एक दंतकथा", "शतरंज के इतिहास में अमर",
        ],
    },
}
CTA_TEXTS = {
    "pl": [
        "Jeśli podoba Wam się ten film, zostawcie łapkę w górę i zasubskrybujcie kanał. To bardzo pomaga.",
        "Zanim pójdziemy dalej: jeśli ta partia Was wciąga, dajcie łapkę w górę i subskrybujcie kanał. To naprawdę pomaga.",
        "Jeśli doceniacie takie analizy, polubcie ten film i zasubskrybujcie kanał, to bardzo nam pomaga.",
    ],
    "de": [
        "Wenn euch das Video gefällt, lasst ein Like da und abonniert den Kanal. Das hilft uns sehr.",
        "Bevor es weitergeht: Wenn euch diese Partie packt, gebt dem Video ein Like und abonniert den Kanal. Das hilft wirklich.",
        "Wenn ihr solche Analysen mögt, gebt dem Video ein Like und abonniert den Kanal, das hilft uns enorm.",
    ],
    "en": [
        "If you're enjoying this video, give it a like and subscribe. It really helps the channel.",
        "Before we go on: if this game has you hooked, hit like and subscribe. It really helps.",
        "If you like breakdowns like this, give the video a like and subscribe, it helps the channel a lot.",
    ],
}
CTA_TEXTS["hi"] = [
    "अगर आपको यह वीडियो पसंद आ रहा है, तो लाइक करें और चैनल को सब्सक्राइब करें। इससे हमें बहुत मदद मिलती है।",
    "आगे बढ़ने से पहले: अगर यह बाज़ी आपको रोमांचक लग रही है, तो लाइक और सब्सक्राइब ज़रूर करें।",
    "अगर आपको ऐसे विश्लेषण पसंद हैं, तो वीडियो को लाइक करें और चैनल को सब्सक्राइब करें, इससे चैनल को बहुत मदद मिलती है।",
]
# UK / RU / TR — forma "ми" / "мы" / "biz" (bez rodzaju gramatycznego lektora); NIE zweryfikowane przez native speakera
TEXTS["uk"] = {
    "greeting": ["Привіт, я {name}.", "Вітаю, з вами {name}.", "Привіт усім, я {name}."],
    "greeting_no_name": ["Привіт.", "Вітаю.", "Привіт усім."],
    "intro": [
        "Сьогодні розберемо партію, яка назавжди увійшла в історію шахів.",
        "Сьогодні подивимося одну з найнапруженіших партій в історії.",
        "Сьогодні на нас чекає партія, що увійшла в історію світових шахів.",
        "Сьогодні розберемо партію, яку варто знати кожному шахісту.",
        "Сьогодні подивимося партію, яка змінила історію шахів.",
        "Сьогодні розберемо партію, яку кожен любитель шахів має побачити хоча б раз.",
        "Сьогодні розберемо одну з найзахопливіших партій в історії шахів.",
        "Сьогодні подивимося партію, про яку шахісти говорять досі. Зараз побачите чому.",
        "Сьогоднішню партію варто знати, навіть якщо ви тільки починаєте грати в шахи.",
        "Сьогодні розберемо партію, без якої важко розповісти історію шахів.",
        "Сьогодні подивимося партію, яка й досі захоплює шахістів у всьому світі.",
    ],
    "outro": "Дякуємо за перегляд. Якщо вам подобаються шахи, поставте вподобайку і підпишіться на канал.",
    "title_hooks": [
        "Партія, яку треба знати", "Партія, що увійшла в історію", "Легендарна партія", "Класика, яку варто знати",
        "Одна з найвідоміших партій", "Партія, яку треба побачити", "Шахова легенда", "Назавжди в історії шахів",
    ],
}
TEXTS["ru"] = {
    "greeting": ["Привет, я {name}.", "Здравствуйте, с вами {name}.", "Всем привет, я {name}."],
    "greeting_no_name": ["Привет.", "Здравствуйте.", "Всем привет."],
    "intro": [
        "Сегодня разберём партию, которая навсегда вошла в историю шахмат.",
        "Сегодня посмотрим одну из самых напряжённых партий в истории.",
        "Сегодня нас ждёт партия, вошедшая в историю мировых шахмат.",
        "Сегодня разберём партию, которую стоит знать каждому шахматисту.",
        "Сегодня посмотрим партию, которая изменила историю шахмат.",
        "Сегодня разберём партию, которую каждый любитель шахмат должен увидеть хотя бы раз.",
        "Сегодня разберём одну из самых захватывающих партий в истории шахмат.",
        "Сегодня посмотрим партию, о которой шахматисты говорят до сих пор. Сейчас увидите почему.",
        "Сегодняшнюю партию стоит знать, даже если вы только начинаете играть в шахматы.",
        "Сегодня разберём партию, без которой трудно рассказать историю шахмат.",
        "Сегодня посмотрим партию, которая до сих пор восхищает шахматистов по всему миру.",
    ],
    "outro": "Спасибо за просмотр. Если вам нравятся шахматы, поставьте лайк и подпишитесь на канал.",
    "title_hooks": [
        "Партия, которую нужно знать", "Партия, вошедшая в историю", "Легендарная партия", "Классика, которую стоит знать",
        "Одна из самых известных партий", "Партия, которую нужно увидеть", "Шахматная легенда", "Навсегда в истории шахмат",
    ],
}
TEXTS["tr"] = {
    "greeting": ["Merhaba, ben {name}.", "Merhaba arkadaşlar, ben {name}.", "Hoş geldiniz, ben {name}."],
    "greeting_no_name": ["Merhaba.", "Merhaba arkadaşlar.", "Hoş geldiniz."],
    "intro": [
        "Bugün satranç tarihine geçmiş bir oyunu inceleyeceğiz.",
        "Bugün tarihin en heyecanlı oyunlarından birine bakacağız.",
        "Bugün dünya satranç tarihine adını yazdırmış bir oyun bizi bekliyor.",
        "Bugün her satranççının bilmesi gereken bir oyunu inceleyeceğiz.",
        "Bugün satranç tarihini değiştiren bir oyuna bakacağız.",
        "Bugün her satranç severin en az bir kez görmesi gereken bir oyunu inceleyeceğiz.",
        "Bugün satranç tarihinin en sürükleyici oyunlarından birini inceleyeceğiz.",
        "Bugün satranççıların hâlâ konuştuğu bir oyuna bakacağız. Nedenini birazdan göreceksiniz.",
        "Satranca yeni başlamış olsanız bile bugünkü oyunu bilmeye değer.",
        "Bugün satranç tarihini anlatırken atlanamayacak bir oyunu inceleyeceğiz.",
        "Bugün dünyanın dört bir yanındaki satranççıları hâlâ büyüleyen bir oyuna bakacağız.",
    ],
    "outro": "İzlediğiniz için teşekkürler. Satrancı seviyorsanız videoyu beğenin ve kanala abone olun.",
    "title_hooks": [
        "Bilmeniz Gereken Bir Oyun", "Tarihe Geçen Oyun", "Efsane Oyun", "Bilinmesi Gereken Bir Klasik",
        "En Ünlü Oyunlardan Biri", "Mutlaka Görmeniz Gereken Oyun", "Bir Satranç Efsanesi", "Satranç Tarihinde Ölümsüz",
    ],
}
CTA_TEXTS["uk"] = [
    "Якщо вам подобається це відео, поставте вподобайку і підпишіться на канал. Це дуже допомагає.",
    "Перш ніж підемо далі: якщо ця партія вас захопила, поставте лайк і підпишіться на канал. Це справді допомагає.",
    "Якщо вам цікаві такі розбори, вподобайте відео і підпишіться на канал, це дуже нам допомагає.",
]
CTA_TEXTS["ru"] = [
    "Если вам нравится это видео, поставьте лайк и подпишитесь на канал. Это очень помогает.",
    "Прежде чем идти дальше: если эта партия вас захватила, поставьте лайк и подпишитесь на канал. Это правда помогает.",
    "Если вам интересны такие разборы, поставьте лайк и подпишитесь на канал, это очень нам помогает.",
]
CTA_TEXTS["tr"] = [
    "Bu videoyu beğendiyseniz beğen butonuna basın ve kanala abone olun. Bu bize çok yardımcı oluyor.",
    "Devam etmeden önce: bu oyun ilginizi çektiyse videoyu beğenin ve kanala abone olun. Gerçekten çok yardımcı oluyor.",
    "Bu tür analizleri seviyorsanız videoyu beğenin ve kanala abone olun, kanala çok faydası oluyor.",
]
CTA = CTA_TEXTS[L.code]
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
    """Powitanie bez przedstawiania się (decyzja właściciela) + zapowiedź partii.
    Imię (HOST_NAME) używane tylko, gdy przekazane jawnie: intro_for(game, name="…")."""
    if name:
        greet = GREETING[_index(game, GREETING, 1, "greet")].format(name=name)
    else:
        greet = GREETING_NO_NAME[_index(game, GREETING_NO_NAME, 1, "greet")]
    return f"{greet} {INTRO[_index(game, INTRO, 0, 'intro')]}"


def cta_for(game: dict | None) -> str:
    """Prośba o łapkę i subskrypcję w środku odcinka."""
    return CTA[_index(game, CTA, 2, "cta")]


def title_hook_for(game: dict | None) -> str:
    return TITLE_HOOKS[_index(game, TITLE_HOOKS, 3, "title")]
