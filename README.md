# szachy — pipeline odcinków o słynnych partiach (PL)

PGN -> walidacja (python-chess) -> scenariusz z markerami {{m:N}} -> Inworld TTS-2 (pl-PL, timestampy słów)
-> animacja szachownicy (Pillow + sprite'y z chess.svg) -> ffmpeg.

## Lokalnie
    pip install -r requirements.txt
    cd src
    python main.py --pgn ../games/opera_1858.pgn --script ../scripts/opera_1858.json --out ../out/opera.mp4 --check-only
    python main.py ... --dry-run
    INWORLD_API_KEY=... INWORLD_VOICE_ID=... python main.py ...

## Generowanie scenariusza
    OPENAI_API_KEY=... python script_gen.py --pgn ../games/<nazwa>.pgn --out ../scripts/<nazwa>.json
    python script_gen.py --pgn ... --out ... --table-only   # podgląd wejścia dla LLM
Stockfish (PATH, STOCKFISH_PATH lub --stockfish) dodaje oceny; bez niego LLM nie może oceniać ruchów.

## Zasady
- Ruchy w lektorze pochodzą tylko z PGN (markery), LLM nie może ich przekręcić.
- Surowa notacja w tekście scenariusza = błąd walidacji.
- PGN każdej partii zweryfikuj w dwóch niezależnych bazach przed nagraniem.

## Paczki do ręcznego uploadu (tryb domyślny)
Co 3 dni (10:00 Europe/Kyiv) bot przygotowuje z wyprzedzeniem paczkę: video.mp4, cover.jpg, opis.txt
(planowana data, tytuł, opis, tagi). Gdzie jej szukać:
- GitHub -> Releases (np. `ep001-anderssen_kieseritzky_1851`);
- Telegram, jeśli ustawione sekrety TELEGRAM_BOT_TOKEN i TELEGRAM_CHAT_ID (okładka, wideo do 50 MB, tekst);
- artefakt przebiegu Actions (zip, 14 dni).

## Autopublikacja (PUBLISH_MODE=youtube)
    python src/scheduler.py --plan                 # co i kiedy wyjdzie
    python src/scheduler.py --dry-tts              # test bez Inworld i bez uploadu
GitHub Actions `publish-episodes` uruchamia się codziennie i trzyma 2 odcinki zaplanowane naprzód
(upload jako prywatny z `publishAt`). Pierwsze uruchomienie: Actions -> publish-episodes -> Run workflow, `first_day`.

Konfiguracja YouTube (jednorazowo):
1. Google Cloud: projekt, włączone YouTube Data API v3, ekran zgody OAuth, OAuth client typu Desktop.
2. `python src/youtube_auth.py client_secret.json` -> sekrety YT_CLIENT_ID, YT_CLIENT_SECRET, YT_REFRESH_TOKEN.
3. Audyt API (formularz YouTube API Services) — bez niego filmy zostaną zablokowane jako prywatne.

## Katalog partii
`catalog/games.json` (100 partii, pole `n` = kolejność), `catalog/LISTA.md` — podgląd.
PGN: `python src/pgn_collect.py --source nazwa=ścieżka ...` (≥2 zgodne kolekcje -> games/<id>.pgn).
