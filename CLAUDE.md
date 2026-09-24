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
- src/players.py — nazwy do kadru (nadpisania *_first/*_last w katalogu), zdjęcia assets/players/<slug>.jpg + .json
- src/fetch_portraits.py — zdjęcia: Wikidata P18 -> Commons, tylko PD/CC0/CC BY/CC BY-SA, pełna zgodność nazwy + zawód szachista + rok urodzenia; raport assets/players/REPORT.md; atrybucja w kadrze i w opisie YouTube
- src/main.py — CLI: --check-only, --dry-run
- src/script_gen.py — PGN -> tabela półruchów (N, SAN, FEN, ocena Stockfisha) -> OpenAI Responses API (gpt-5.5, SCRIPT_MODEL; OPENAI_API_KEY) z prompts/script_system_pl.md -> build_segments -> do 3 poprawek -> scripts/<nazwa>.json
- prompts/script_system_pl.md — system prompt do generowania scenariuszy
- catalog/games.json — 100 partii (kolejność n, metadane zweryfikowane wyszukiwaniem, status PGN); catalog/LISTA.md generuje src/catalog_list.py
- src/pgn_collect.py — PGN z ≥2 niezależnych kolekcji (mirror rozim/ChessData: PgnMentor, ChessNostalgia, Chessopolis, RebelSite, WorldChampionships, Kingbase, Twic, Old…; + famous_games, ChessPGN); zgodność ruchów, wyniku, rundy i liczby ruchów
- src/scheduler.py — co 3 dni 10:00 Europe/Kyiv; bufor 2 odcinków; upload jako private + publishAt (YouTube publikuje sam); stan w state/schedule.json
- src/youtube_upload.py, src/youtube_auth.py — YouTube Data API (OAuth refresh token)
- .github/workflows/publish.yml — cron codziennie 03:17 UTC, commit stanu do repo
- .github/workflows/build.yml — workflow_dispatch, sekrety INWORLD_API_KEY, INWORLD_VOICE_ID
- sekrety publish.yml: OPENAI_API_KEY, INWORLD_API_KEY, INWORLD_VOICE_ID, YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN

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
