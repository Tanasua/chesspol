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
- src/main.py — CLI: --check-only, --dry-run; na końcu każdego odcinka stały segment OUTRO (podziękowanie, prośba o like i subskrypcję); na samym początku powitanie prowadzącego (segment intro, imię z HOST_NAME albo INWORLD_VOICE_ID); muzyka w tle assets/music/the_daily_ostinato.mp3 (Suno; pętla, MUSIC_GAIN_DB=-20, fade-in 2 s, fade-out 6 s na końcu; MUSIC="" albo --no-music wyłącza)
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
- src/deliver.py, src/cover.py — paczka out/packages/epNNN-<id>/ (video.mp4, cover.jpg 1280x720, opis.txt: data, tytuł, opis [zachęta z LLM, karta partii, rozdziały z czasami z out/<id>.timing.json, PGN, atrybucja zdjęć, zdanie o weryfikacji PGN; bez akapitu o AI — decyzja właściciela], tagi) -> GitHub Release + opcjonalnie Telegram (sekrety TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID; wideo ≤50 MB)
- Telegram/paczka: teksty dla właściciela PO UKRAIŃSKU (podpisy, nagłówki, data "пт, 02.10.2026 о 10:00 (за Києвом)"),
  tytuł/opis/tagi w języku kanału, każde w osobnym bloku <pre> (kopiowanie jednym dotknięciem); opis dzielony na części ≤3500 znaków
- Tytuł YouTube: "<KICKER> <title> | Białe – Czarne (rok)"; kicker = 1–3 słowa WERSALIKAMI z "!" od LLM (pole "kicker",
  walidacja w script_check); stare scenariusze bez kickera -> dopisek z phrases.TITLE_HOOKS
- src/youtube_upload.py, src/youtube_auth.py — YouTube Data API (OAuth refresh token)
- .github/workflows/publish.yml — cron codziennie 03:17 UTC, INTERVAL_DAYS=1 (1 odcinek dziennie; maks. 2 z nowością), commit stanu do repo
- NOWOŚCI: src/news.py (+ .github/workflows/news.yml, workflow_dispatch: kanał, turniej/link Lichess, test). Lichess API
  (broadcast search / tour / round PGN) -> format nokaut/kołowy -> wybór JEDNEJ partii bez pytania (etap, tempo, wynik,
  ranking, dramat wg Stockfisha, partia rozstrzygająca mecz, wzmianki r/chess) -> portrety po FIDE ID (Wikidata P1440)
  -> src/bracket.py: plansza na początek (drabinka z przekreślonymi odpadłymi / tabela; stan PRZED partią) -> catalog/news.json,
  facts/<id>.md (fakty policzone z PGN) -> script_gen -> main.py --preroll -> paczka (tag news[-test]-…, okładka z plakietką turnieju).
  Nazwiska z formatu FIDE w PGN ("Ding, Liren" -> DING). lichess.org zablokowany w środowisku deweloperskim — test tylko w Actions.
- FLAGI: src/countries.py — kraj gracza z Wikidata P1532 (z datami od/do; fallback P27), pamięć assets/players/countries.json
  (uzupełnia fetch_portraits.py dla katalogu i news.py dla turniejów). assets/flags/<iso>.svg (flag-icons, MIT; ru.svg i by.svg
  usunięte). Zamiast flag tekst: RU (Rosja, Imperium Ros., RFSRR), BY, SU (ZSRR), DE (III Rzesza 1933–45) — decyzja właściciela.
  Flagi na okładce (pod portretami) i w drabince; nowości: +2.5 pkt za partię z graczem z kraju kanału (Polak / Niemiec).
- KANAŁY: src/lang.py (CHANNEL=pl domyślnie | de). Wspólne: katalog, PGN, zdjęcia, render, muzyka, Telegram (ten sam czat, flaga 🇵🇱/🇩🇪).
  Osobne: kolejność (n / n_de, seed 20261001), stan (state/schedule.json / schedule_de.json), scenariusze (scripts/ / scripts_de/),
  wideo (out/ / out/de/), tagi Release (ep001-… / de-ep001-…), prompt (prompts/script_system_<kod>.md), zapis ruchów
  (pl_notation.py / de_notation.py: K D T L S, "Springer nach eff drei"), zwroty (phrases.TEXTS), teksty opisu (lang.L.t).
  Pola katalogu *_de: label_de, event_de, site_de, black_de/black_last_de (Die Welt, Herzog von Braunschweig…); nazwiska — pisownia bazowa.
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
