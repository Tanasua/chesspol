# Projekt: kanał YouTube o słynnych partiach szachowych (PL)

Kontekst dla Claude Code. Komunikacja z właścicielem projektu: po ukraińsku.
Treść kanału (lektor, napisy): po polsku.

## Pipeline
PGN -> walidacja (python-chess) -> scenariusz JSON z markerami -> Inworld TTS-2 (pl-PL,
timestampy słów) -> animacja szachownicy (Pillow + sprite'y z chess.svg przez cairosvg) -> ffmpeg (stdin rawvideo).

Pliki:
- src/pgn_loader.py — parsowanie PGN, legalność ruchów, zgodność mata z wynikiem
- src/pl_notation.py — polska notacja (K H W G S) i zapis słowny ruchów dla TTS
- src/script_check.py — markery {{m:N}} (ruch czytany, tekst ruchu wstawia system) i {{s:N}} (ruch cichy); twarda walidacja
- src/tts_inworld.py — POST https://api.inworld.ai/tts/v1/voice, timestampType WORD, cache na dysku, dopasowanie słów przez difflib
- src/render.py — klatki 1920x1080: szachownica 1000x1000 na środku (białe na dole); lewa kolumna: czarne u góry, białe u dołu (zdjęcie, imię, NAZWISKO, pasek przy stronie na ruchu), pośrodku rok + catalog.label_pl; prawa kolumna: bieżący ruch + lista ruchów (tylko rozegrane); animacja ruchu, schedule() bez nachodzenia animacji
- Krój: Montserrat (assets/fonts, SIL OFL — OFL.txt), render._font(size, bold, weight=regular|medium|semibold|bold|extrabold|black);
  domyślnie Medium / Bold; fallback DejaVu. Okładka: tytuł dopasowywany 64→40 px do 3 wierszy; rok nie dubluje się w plakietce.
- src/players.py — nazwy do kadru (nadpisania *_first/*_last w katalogu), zdjęcia assets/players/<slug>.jpg + .json
- src/fetch_portraits.py — zdjęcia: Wikidata P18 -> Commons, tylko PD/CC0/CC BY/CC BY-SA, pełna zgodność nazwy + zawód szachista + rok urodzenia; raport assets/players/REPORT.md; atrybucja w kadrze i w opisie YouTube
- src/main.py — CLI: --check-only, --dry-run; na końcu każdego odcinka stały segment OUTRO (podziękowanie, prośba o like i subskrypcję); na samym początku powitanie BEZ przedstawiania się (segment intro; decyzja właściciela); w połowie segment cta (phrases.CTA_TEXTS: łapka + subskrypcja) przed rozdziałem najbliższym środka; muzyka assets/music/the_daily_ostinato.mp3 (Suno; pętla, MUSIC_GAIN_DB=-20) TYLKO na początku (hak + powitanie, potem cichnie przez 4 s) i na końcu (wraca przez 6 s, pełna od outro, fade-out 6 s) — w środku sam lektor (decyzja właściciela); MUSIC="" albo --no-music wyłącza
- HAK (cold open): pole scenariusza "hook" {"text", "ply"} — 1–2 zdania PRZED powitaniem (intryga bez spoilera; typy: stawka,
  paradoks, pytanie, odliczanie; fakty/oceny jak w scenariuszu; bez ruchów, markerów i cyfr; 40–300 znaków — script_check.build_hook).
  W tym czasie szachownica pokazuje pozycję po półruchu "ply" (render_video(flash=...)), potem powitanie i partia od startu;
  plansza nowości (preroll) przesunięta za hak. script_gen wymaga haka; stare scenariusze bez haka działają jak dawniej.
- PAUZA DO NAMYSŁU: marker {{p}} w tekście (maks. 3 na odcinek, zawsze przed {{m:N}} w tym samym segmencie) — lektor
  zadaje pytanie, potem THINK_SEC=4 s ciszy (main.insert_silence, szachownica stoi), potem ruch (decyzja właściciela: 3–5 s).
- KLUCZOWE MOMENTY: src/key_moments.py (Stockfish, zasady 1 i 3) — ofiara (≥3 pkt materiału, nie wraca po 1/3/5 półruchach,
  ocena grającego nie spada, przewaga przed ≤4 piony) albo zwrot oceny ≥2 piony (partia nierozstrzygnięta); maks. 2 na partię,
  odstęp ≥8, bez 2 ostatnich półruchów; wariant silnika po ruchu (≤4 półruchy, ucięty przy "tam i z powrotem"; pomijamy, gdy
  = dalszy ciąg partii). script_gen dodaje je do danych dla LLM i do scenariusza (script["key_moments"]); LLM MUSI wstawić
  {{v:N}} raz zaraz po markerze N (script_check). System czyta wariant w notacji kanału i pokazuje "alternatywną
  rzeczywistość" (Renderer.alternate, render.variation_timeline): szachownica szarzeje (FADE 0.5 s), na słowie ruchu wyrasta
  strzałka (pod figurami; zielone = strona kluczowego ruchu, czerwone = przeciwnik, numer), po niej figura naprawdę się rusza;
  najnowsza strzałka nasycona, starsze półprzezroczyste; strzałki na tej samej parze pól biegną równolegle obok siebie;
  po VAR_HOLD=1.6 s figury cofają się w odwrotnej kolejności (REWIND_STEP=0.25 s/ruch), potem wraca kolor.
  Partia stoi do końca (schedule(barriers)).
- Dźwięk figury: src/sfx.py — własna synteza (drewniane 'tok', bicie jaśniejsze z odbiciem), w chwili lądowania figury
  (ANIM_SEC*0.85 po starcie ruchu), SFX_GAIN_DB=-14, --no-sfx wyłącza; miksowany z lektorem przed muzyką.
- Przewijanie pominiętych półruchów: AUTO_STEP 1.25 s/ruch (render.py, maks. 1.5); gdy lektor nie daje czasu, main.py rozcina
  nagranie tuż przed słowem markera i wstawia ciszę (muzyka gra). timing.json zawiera też czasy ruchów (moves, spoken).
- Koniec partii tylko głosem (bez planszy na ekranie — decyzja właściciela): prompty każą powiedzieć, kto się poddał;
  powód wg oceny silnika po ostatnim ruchu: #N -> 'nie uniknie mata', ≥~3 piony -> 'pozycja przegrana', inaczej bez powodu.
- src/phrases.py — powitania (GREETING z imieniem), warianty zapowiedzi (INTRO, 11) i dopisków do tytułu YouTube (TITLE_HOOKS, 8); wybór wg n z katalogu, kolejne odcinki dostają kolejne warianty
- src/script_gen.py — PGN -> tabela półruchów (N, SAN, FEN, ocena Stockfisha) -> OpenAI Responses API (gpt-5.5, SCRIPT_MODEL; OPENAI_API_KEY) z prompts/script_system_pl.md -> build_segments -> do 3 poprawek -> scripts/<nazwa>.json
- prompts/script_system_pl.md — system prompt do generowania scenariuszy
- catalog/games.json — 100 partii (kolejność n, metadane zweryfikowane wyszukiwaniem, status PGN); catalog/LISTA.md generuje src/catalog_list.py
- src/pgn_collect.py — PGN z ≥2 niezależnych kolekcji (mirror rozim/ChessData: PgnMentor, ChessNostalgia, Chessopolis, RebelSite, WorldChampionships, Kingbase, Twic, Old…; + famous_games, ChessPGN); zgodność ruchów, wyniku, rundy i liczby ruchów
- src/scheduler.py — co 3 dni 10:00 Europe/Kyiv; bufor 2 odcinków; PUBLISH_MODE=manual (domyślnie): paczka do ręcznego uploadu; PUBLISH_MODE=youtube: upload private + publishAt; stan w state/schedule.json
- src/deliver.py, src/cover.py — paczka out/packages/epNNN-<id>/ (<tytuł YouTube>.mp4 — nazwa pliku z tytułu (deliver.video_filename), cover.jpg 1280x720, opis.txt: data, tytuł, opis [zachęta z LLM, karta partii, rozdziały z czasami z out/<id>.timing.json, PGN, atrybucja zdjęć, zdanie o weryfikacji PGN; BEZ akapitu o AI, BEZ zapisu ruchów i BEZ listy źródeł zdjęć — decyzje właściciela; autor/licencja zdjęcia tylko w kadrze], tagi) -> GitHub Release + opcjonalnie Telegram (sekrety TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID; wideo ≤50 MB)
- STRZAŁKI NA OKŁADCE: src/cover_marks.py (Stockfish, zasada nr 3): niebieska = ostatni ruch (żółta zlewała się z podświetleniem); czerwona = groźba zwycięzcy w pozycji
  końcowej (ruch zerowy przegrywającego, ≥2 piony/mat, bez strzałek na sąsiednie pole); znak w kółku: seed % 3 -> '!' / '?' / brak
  ('!' = ruch zwycięzcy = 1. wybór silnika lub ≤0.5 piona gorszy i pozycja wygrana; '?' = ostatni ruch przegrywającego traci ≥1.5 piona,
  z pomarańczową strzałką); bez silnika tylko niebieska strzałka. Okładka z tymi znakami idzie też do OpenAI.
  Rysunek: warstwy pola -> cienkie strzałki (grot na skraju pola) -> figury; mały znak na rogu pola — figury nigdy nie zasłonięte
  (decyzja właściciela: OpenAI nie może zgadywać, jaka figura stoi pod strzałką).
- KRAJ W KADRZE: pod nazwiskiem flaga (albo skrót RU/BY/SU/DE) + nazwa kraju w języku kanału (src/country_names.py,
  Renderer._name); podpis turnieju w środku skraca się do miejsca między graczami.
- Kraje: okresy bez dat dla ZSRR / III Rzeszy dostają lata istnienia państwa (countries.STATE_YEARS) — Spasski 1972 = SU, nie FR.
- OKŁADKA AI: src/cover_ai.py — nasza okładka -> OpenAI Images API edit (COVER_AI_MODEL, domyślnie gpt-image-2.5-sunburst,
  fallback gpt-image-2; 1536x864 -> 1280x720) z promptem właściciela (PROMPT, po ukraińsku, dosłownie; + jego "строге правило": figury i strzałki na tych samych polach, strzałki mogą być neonowe) -> cover_ai.jpg w paczce
  i Release; Telegram: album [nasza, AI] do porównania + cover_ai.jpg jako plik. Błąd/odmowa nie blokuje odcinka. COVER_AI=0 wyłącza.
- Telegram/paczka: teksty dla właściciela PO UKRAIŃSKU (podpisy, nagłówki, data "пт, 02.10.2026 о 10:00 (за Києвом)"),
  tytuł/opis/tagi w języku kanału, każde w osobnym bloku <pre> (kopiowanie jednym dotknięciem); opis dzielony na części ≤3500 znaków
- OKŁADKA vs TYTUŁ YOUTUBE (decyzja właściciela: różne słowa). Okładka: "<KICKER> <title>" (pola LLM kicker + title;
  scheduler.cover_text). Tytuł YouTube (scheduler.yt_title, maks. 100 zn.): "<yt_hook> | Nazwisko – Nazwisko (turniej, rok)
  — <yt_detail>"; yt_hook = inna fraza (≤45 zn., script_check odrzuca, gdy >50% słów jak na okładce), yt_detail = kto co
  zrobił (≤60 zn., fakty jak w scenariuszu); turniej z katalogu tylko gdy ważny (IMPORTANT_EVENT_RE: MŚ, pretendenci,
  olimpiada, mistrzostwa, puchar świata, finał); gdy za długo — najpierw bez turnieju, potem bez szczegółu. Nazwiska w
  pisowni języka kanału (catalog/surnames.json, players.local_surname, ta sama w kadrze). Starsze scenariusze bez yt_hook:
  "<KICKER> <title> | Nazwisko – Nazwisko (rok)" albo dopisek z phrases.TITLE_HOOKS.
- src/youtube_upload.py, src/youtube_auth.py — YouTube Data API (OAuth refresh token)
- scheduler --game <id> (workflow_dispatch input "game" w publish*.yml): wskazana partia na najbliższy odcinek, poza kolejką.
- .github/workflows/publish.yml — cron codziennie 03:17 UTC, INTERVAL_DAYS=1 (1 odcinek dziennie; maks. 2 z nowością), commit stanu do repo
- NOWOŚCI: src/news.py (+ .github/workflows/news.yml, workflow_dispatch: kanał, turniej/link Lichess, test). Lichess API
  (broadcast search / tour / round PGN) -> format nokaut/kołowy -> wybór JEDNEJ partii bez pytania (etap, tempo, wynik,
  ranking, dramat wg Stockfisha, partia rozstrzygająca mecz, wzmianki r/chess) -> portrety po FIDE ID (Wikidata P1440)
  -> src/bracket.py: plansza na początek (drabinka z przekreślonymi odpadłymi / tabela; stan PRZED partią) -> catalog/news.json,
  facts/<id>.md (fakty policzone z PGN) -> script_gen -> main.py --preroll -> paczka (tag news[-test]-…, okładka z plakietką turnieju).
  Nazwiska z formatu FIDE w PGN ("Ding, Liren" -> DING). lichess.org zablokowany w środowisku deweloperskim — test tylko w Actions.
- AUTOŚLEDZENIE: src/news_watch.py + .github/workflows/news_watch.yml (cron 21:17 UTC, codziennie): Lichess /api/broadcast/top,
  rundy zakończone w ostatnich 30 h, turnieje z listy WATCH albo tier ≥5, bez blitz/bullet/Freestyle; dla każdego kanału z głosem
  1 nowość dziennie (news.py --round-id: wybór tylko z tej rundy, kontekst z całego turnieju); stan state/news_watch.json.
- FLAGI: src/countries.py — kraj gracza z Wikidata P1532 (z datami od/do; fallback P27), pamięć assets/players/countries.json
  (uzupełnia fetch_portraits.py dla katalogu i news.py dla turniejów). assets/flags/<iso>.svg (flag-icons, MIT; ru.svg i by.svg
  usunięte). Zamiast flag tekst: RU (Rosja, Imperium Ros., RFSRR), BY, SU (ZSRR), DE (III Rzesza 1933–45) — decyzja właściciela.
  Flagi na okładce (pod portretami) i w drabince; nowości: +2.5 pkt za partię z graczem z kraju kanału (Polak / Niemiec).
- KANAŁY: src/lang.py (CHANNEL=pl domyślnie | de | en | hi). Wspólne: katalog, PGN, zdjęcia, render, muzyka, Telegram (ten sam czat, flaga 🇵🇱/🇩🇪).
  Osobne: kolejność (n / n_de, seed 20261001), stan (state/schedule.json / schedule_de.json), scenariusze (scripts/ / scripts_de/),
  wideo (out/ / out/de/), tagi Release (ep001-… / de-ep001-…), prompt (prompts/script_system_<kod>.md), zapis ruchów
  (pl_notation.py / de_notation.py: K D T L S, "Springer nach eff drei"), zwroty (phrases.TEXTS), teksty opisu (lang.L.t).
  Pola katalogu *_de: label_de, event_de, site_de, black_de/black_last_de (Die Welt, Herzog von Braunschweig…); nazwiska — pisownia bazowa.
- RUBRYKA KRAJOWA: catalog/national_<kraj>.json (pl, de, us — wg Channel.country/code; pola jak games.json + n), PGN w games/,
  weryfikacja: pgn_collect.py --catalog catalog/national_us.json. scheduler: historia i rubryka krajowa na przemian
  (episode.rubric), gdy jednej brak — druga. players.catalog_entry i fetch_portraits widzą też katalogi krajowe.
  national_us.json: 24 zwycięstwa Amerykanów nad mistrzami/pretendentami (bez duplikatów głównego katalogu); 22 z PGN
  w ≥2 kolekcjach, Morphy–Anderssen 1858 i Christiansen–Karpov 1993 — 1 źródło (scheduler pomija). national_pl/de — do zrobienia.
  national_in.json (kanał hi): 19 zwycięstw Indusów (Anand: MŚ 2000/2007/2008/2010/2012/2014, PCA 1995, pretendenci; Sultan Khan
  1932; Harikrishna 2016; Gukesh/Praggnanandhaa 2023–24) — 14 zweryfikowanych; Gukesh–Caruana i Gukesh–Firouzja 2024,
  Praggnanandhaa–Carlsen 2024, Praggnanandhaa–Caruana 2023 i Anand–Kasparov 1991 tylko w 1 kolekcji (TWIC) — czekają na drugie
  źródło. Świeże partie 2025–26 (Gukesh, Pragg, Arjun, Divya, Vaishali) — przez NOWOŚCI (Lichess). Hindi: HOME_BONUS=8 w news.py,
  news_watch dopuszcza turnieje indyjskie (INDIA regex, także niższy tier) tylko dla hi i daje im pierwszeństwo (+40).
  Fakty (facts/): 22 partie głównego katalogu; wątpliwe rundy w .sources.md (Portisch r4, Shirov r9, Botvinnik–Portisch r7,
  Lilienthal r5, Sämisch r6 — niepotwierdzone).
- FAKTY: facts/<id>.md (EN, punkty potwierdzone ≥2 niezależnymi źródłami) + facts/<id>.sources.md (URL-e, nie trafiają do LLM).
- KANAŁ EN (USA): CHANNEL=en — kolejność n_en (seed 20261003), label_en/event_en, black_en (The World, Duke of Brunswick…),
  en_notation.py ("knight to F three", "E takes D five", "castles kingside"; ekran: zwykły SAN), prompts/script_system_en.md,
  scripts_en/, out/en/, state/schedule_en.json, tag en-…, flaga 🇺🇸, "swój" gracz = us (Channel.country);
  .github/workflows/publish_en.yml — cron 06:17 UTC, publikacja 10:00 America/New_York (w Telegramie także czas kijowski);
  sekrety ELEVENLABS_VOICE_ID_EN, zmienna HOST_NAME_EN; news.yml obsługuje kanał en.
- KANAŁ HI (Indie, PRZYGOTOWANY, NIEAKTYWNY do czasu sekretu ELEVENLABS_VOICE_ID_HI): CHANNEL=hi — kolejność n_hi (seed 20261004),
  pola katalogu *_hi z fallbackiem na *_en (Channel.fallback), hi_notation.py (HI_PIECES=hindi: राजा रानी हाथी ऊँट घोड़ा प्यादा —
  wg hindi wersji chess.com; =english: किंग क्वीन रूक बिशप नाइट; "ऊँट बी छह पर काटता है, शह"; ekran: SAN), krój Hind
  (assets/fonts/hind, SIL OFL; Pillow z raqm do dewanagari), prompts/script_system_hi.md (instrukcje po angielsku, tekst dla
  widza w hindi), phrases/CTA hi (forma "हम"), scripts_hi/, out/hi/, state/schedule_hi.json, tag hi-, flaga 🇮🇳, "swój" = in;
  .github/workflows/publish_hi.yml — cron 08:17 UTC, publikacja 18:00 Asia/Kolkata; news.yml / news_watch obsługują hi.
  NIE zweryfikowane przez native speakera: nazwy figur, zwroty, teksty opisu — odsłuchać 1–2 pierwsze odcinki.
- src/tts_elevenlabs.py — ElevenLabs /v1/text-to-speech/{voice}/with-timestamps (alignment znaków -> słowa), ELEVENLABS_MODEL
  (domyślnie eleven_multilingual_v2); NIE zweryfikowane na prawdziwym kluczu
- .github/workflows/publish_de.yml — kanał niemiecki, cron 04:47 UTC, ta sama grupa concurrency co publish.yml; bez klucza ElevenLabs pomija.
  Sekrety: ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID_DE (+ wspólne OPENAI_API_KEY, TELEGRAM_*); zmienne: HOST_NAME_DE, opcjonalnie ELEVENLABS_MODEL
- .github/workflows/build.yml — workflow_dispatch, sekrety INWORLD_API_KEY, INWORLD_VOICE_ID
- sekrety publish.yml: OPENAI_API_KEY, INWORLD_API_KEY, INWORLD_VOICE_ID; opcjonalnie TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID; tylko w trybie youtube: YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN

## Zasady nienaruszalne
1. Ruchy w lektorze pochodzą WYŁĄCZNIE z PGN przez markery. LLM nigdy nie zapisuje ruchów sam.
   Surowa notacja w tekście scenariusza = błąd walidacji (nie osłabiać tej reguły).
2. Fakty historyczne tylko z nagłówków PGN lub plików facts/<nazwa>.md. Zero dopowiadania z pamięci modelu.
3. Oceny ("błąd", "najlepszy ruch") tylko z potwierdzeniem silnika.
4. PGN każdej partii weryfikować w dwóch niezależnych bazach.
5. Przy zmianach kodu podawać właścicielowi pełną treść pliku, nie diff.

## Stan
- Zweryfikowane: dry-run renderu na games/opera_1858.pgn (pozycja matowa poprawna, animacja roszady OK).
- NIE zweryfikowane: realne wywołanie Inworld (format odpowiedzi sprawdzić przy pierwszym prowadzeniu),
  polska gramatyka scenariusza (do korekty przez native speakera).
- scripts/opera_1858.json przepisany (s07 -> s07–s10: kolory figur przy biciach, wyjaśnienie związania wieży d7 i idei 14...He6;
  s01 bez faktów spoza PGN; s03 bez oceny "będą żałować"). Twierdzenia szachowe sprawdzone python-chess. Gramatyka — do native speakera.
- script_gen.py: pętla poprawek przetestowana na atrapie LLM; realne wywołanie API NIE zweryfikowane (brak klucza).
- Katalog: 78/100 partii z PGN potwierdzonym w ≥2 kolekcjach (wrzesień 2026). Uwaga: kolekcje mogą mieć wspólne pochodzenie
  (to mirrory stron, nie niezależne redakcje). Reszta: 1 źródło / brak / konflikt (Fischer–Petrosian 1971: 33...Nxb4 vs Nxf4).
- Zdjęcia: fetch_portraits.py przetestowany tylko na atrapie API (Wikimedia zablokowane w środowisku deweloperskim); pierwsze prawdziwe pobranie w GitHub Actions — przejrzeć REPORT.md.
- YouTube: projekt Google Cloud bez audytu API => filmy z videos.insert blokowane jako prywatne (publishAt nie zadziała). Wymagany audyt.
- Inworld: polski to Tier 1 dla inworld-tts-2; ukraiński tylko Tier 2 w tts-2, brak w tts-1.5.

## Backlog
1. Stockfish: pasek oceny na ekranie + automatyczne wykrywanie punktów zwrotnych (oceny są już w tabeli script_gen).
2. Oceny w scenariuszu opera_1858 (s02 "pasywny wybór", s06 "niemal niedbale") — potwierdzić silnikiem albo usunąć.
3. PGN dla partii bez 2 źródeł (lista w catalog/LISTA.md); rozstrzygnąć konflikt #61.
4. facts/<nazwa>.md dla każdej partii (zweryfikowane fakty historyczne).
5. "Polska nieśmiertelna" (Glücksberg–Najdorf) — w katalogu jako disputed, scheduler ją pomija.
