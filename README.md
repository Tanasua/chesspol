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
