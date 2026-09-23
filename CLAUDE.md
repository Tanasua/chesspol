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
- src/render.py — klatki 1920x1080, animacja ruchu (roszada, bicie w przelocie, promocja), panel ruchów, schedule() bez nachodzenia animacji
- src/main.py — CLI: --check-only, --dry-run
- src/script_gen.py — PGN -> tabela półruchów (N, SAN, FEN, ocena Stockfisha) -> Claude (claude-opus-5, SCRIPT_MODEL) z prompts/script_system_pl.md -> build_segments -> do 3 poprawek -> scripts/<nazwa>.json
- prompts/script_system_pl.md — system prompt do generowania scenariuszy
- .github/workflows/build.yml — workflow_dispatch, sekrety INWORLD_API_KEY, INWORLD_VOICE_ID

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
- Inworld: polski to Tier 1 dla inworld-tts-2; ukraiński tylko Tier 2 w tts-2, brak w tts-1.5.

## Backlog
1. Stockfish: pasek oceny na ekranie + automatyczne wykrywanie punktów zwrotnych (oceny są już w tabeli script_gen).
2. Oceny w scenariuszu opera_1858 (s02 "pasywny wybór", s06 "niemal niedbale") — potwierdzić silnikiem albo usunąć.
3. facts/<nazwa>.md dla każdej partii (zweryfikowane fakty historyczne).
4. Kolejne partie: Rotlewi – Rubinstein, Łódź 1907. "Polska nieśmiertelna" Najdorfa — autentyczność sporna, zweryfikować.
