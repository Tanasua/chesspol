"""Odcinek-nowość: najważniejsza partia z turnieju transmitowanego na Lichess.

  python src/news.py --tournament "Grand Chess Tour Finals 2026" --test     # szukaj po nazwie
  python src/news.py --tournament https://lichess.org/broadcast/<slug>/<id>   # albo link / id
  python src/news.py ... --select-only     # tylko ranking partii (bez scenariusza i renderu)

Kroki:
 1. Lichess API: turniej -> rundy -> PGN każdej rundy (kolejność partii = kolejność rund i w PGN).
 2. Format: nokaut (każdy gracz ma ≤ log2(n) przeciwników, pary grają po kilka partii) albo kołowy.
 3. Wybór JEDNEJ partii (bez pytania właściciela) — punktacja, patrz score_games():
    etap (finał > półfinał > …; w kołowym — późniejsze rundy i liderzy), tempo (klasyczne > rapid > blitz),
    rozstrzygnięcie, siła graczy (średni ranking), dramaturgia wg Stockfisha (największy skok oceny,
    zmiany strony z przewagą), partia rozstrzygająca mecz, wzmianki na r/chess (jeśli Reddit odpowie).
 4. Plansza na początek odcinka: drabinka (nokaut: portrety, nazwiska, wyniki meczów, przekreśleni
    odpadli — stan PRZED tą partią, bez spoilerów) albo tabela (kołowy).
 5. Wpis w catalog/news.json + facts/<id>.md (fakty policzone z danych turnieju), dalej zwykły potok:
    script_gen.py -> main.py (z planszą --preroll) -> paczka (Telegram / Release).
Fakty: tylko z PGN i z wyników policzonych z PGN. Model nie dopowiada nic o bieżących wydarzeniach.
"""
from __future__ import annotations

import argparse
import io
import json
import math
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import chess
import chess.engine
import chess.pgn
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
from lang import L  # noqa: E402
from players import slug, split_name  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
NEWS = ROOT / "catalog" / "news.json"
API = "https://lichess.org/api"
UA = {"User-Agent": "chesspol-news/1.0 (https://github.com/tanasua/chesspol)"}
TC_WEIGHT = {"classical": 1.0, "rapid": 0.6, "blitz": 0.35}
HOME_BONUS = 2.5  # partia z graczem z kraju kanału


# ---------------------------------------------------------------- Lichess
def _get(url: str, **kw) -> requests.Response:
    for attempt in range(4):
        r = requests.get(url, headers=UA, timeout=60, **kw)
        if r.status_code == 429:
            time.sleep(60)
            continue
        if r.status_code >= 500:
            time.sleep(2 ** attempt)
            continue
        r.raise_for_status()
        return r
    r.raise_for_status()
    return r


def find_tour(query: str) -> dict:
    """Jak _find_tour, ale łączy wszystkie transmisje tej samej grupy (np. półfinały i finał to osobne
    'turnieje' na Lichess) w jeden turniej z rundami w kolejności rozgrywania."""
    data = _find_tour(query)
    print("Lichess — klucze odpowiedzi:", sorted(data.keys()), "| tour:", sorted(data.get("tour", {}).keys()))
    base = data["tour"].get("name", "").split(" | ")[0].strip()
    ids = []
    grp = data.get("group")
    if isinstance(grp, dict):
        base = grp.get("name") or base
        ids = [t.get("id") for t in grp.get("tours", []) if t.get("id")]
    if not ids:  # brak informacji o grupie — szukamy transmisji o tej samej nazwie bazowej
        try:
            res = _get(f"{API}/broadcast/search", params={"q": base}).json()
            hits = res.get("currentPageResults") or res.get("results") or []
            ids = [h.get("tour", h)["id"] for h in hits
                   if h.get("tour", h).get("name", "").split(" | ")[0].strip().lower() == base.lower()]
        except requests.RequestException:
            ids = []
    ids = list(dict.fromkeys([data["tour"]["id"], *ids]))
    rounds = []
    for tid in ids:
        part = data if tid == data["tour"]["id"] else _get(f"{API}/broadcast/{tid}").json()
        for r in part.get("rounds", []):
            r = dict(r)
            r["name"] = f"{part['tour'].get('name', '').split(' | ', 1)[-1]} | {r.get('name', '')}" if len(ids) > 1 else r.get("name", "")
            rounds.append(r)
    rounds.sort(key=lambda r: (r.get("startsAt") or r.get("createdAt") or 0))
    print(f"Grupa '{base}': transmisji {len(ids)}, rund {len(rounds)}")
    return {"tour": {**data["tour"], "name": base}, "rounds": rounds}


def _find_tour(query: str) -> dict:
    """Link, id turnieju/rundy albo nazwa -> {'tour':…, 'rounds':[…]}."""
    q = query.strip()
    m = re.search(r"lichess\.org/broadcast/[^/]+/([^/]+)/([A-Za-z0-9]{8})", q)
    if m:  # link do rundy: /broadcast/<tour-slug>/<round-slug>/<roundId>
        data = _get(f"{API}/broadcast/-/-/{m.group(2)}").json()
        return _get(f"{API}/broadcast/{data['tour']['id']}").json()
    m = re.search(r"lichess\.org/broadcast/[^/]+/([A-Za-z0-9]{8})/?$", q) or re.fullmatch(r"([A-Za-z0-9]{8})", q)
    if m:
        return _get(f"{API}/broadcast/{m.group(1)}").json()
    res = _get(f"{API}/broadcast/search", params={"q": q}).json()
    hits = res.get("currentPageResults") or res.get("results") or []
    print("Lichess — wyniki wyszukiwania:", [(h.get("tour", h).get("name"), h.get("tour", h).get("id")) for h in hits[:8]])
    if not hits:
        raise SystemExit(f"Nie znaleziono transmisji: {q!r}")
    words = [w.lower() for w in q.split()]
    best = max(hits, key=lambda h: sum(w in h.get("tour", h).get("name", "").lower() for w in words))
    return _get(f"{API}/broadcast/{best.get('tour', best)['id']}").json()


@dataclass
class G:
    seq: int
    round_idx: int
    round_name: str
    game: chess.pgn.Game
    white: str
    black: str
    result: str
    tc: str
    elo: tuple
    fide: tuple
    score: float = 0.0
    why: list = field(default_factory=list)

    @property
    def pair(self) -> frozenset:
        return frozenset((self.white, self.black))

    def points(self, who: str) -> float:
        if self.result == "1/2-1/2":
            return 0.5
        if self.result == "1-0":
            return 1.0 if who == self.white else 0.0
        if self.result == "0-1":
            return 1.0 if who == self.black else 0.0
        return 0.0


SURNAMES = {}  # nazwa -> nazwisko z zapisu FIDE ("Ding, Liren" -> "Ding", "Gukesh, D" -> "Gukesh")


def norm_name(n: str) -> str:
    """'Caruana, Fabiano' -> 'Fabiano Caruana' (i zapamiętuje nazwisko z formatu FIDE)."""
    n = " ".join((n or "?").split())
    if "," in n:
        last, first = [x.strip() for x in n.split(",", 1)]
        n = f"{first} {last}".strip()
        SURNAMES[n] = last
    return n


def surname(name: str) -> str:
    return SURNAMES.get(name) or split_name(name)[1] or name


def _tc(game: chess.pgn.Game, round_name: str) -> str:
    rn = round_name.lower()
    if "blitz" in rn or "armageddon" in rn:
        return "blitz"
    if "rapid" in rn:
        return "rapid"
    m = re.match(r"(\d+)(?:\+(\d+))?", game.headers.get("TimeControl", ""))
    if m:
        total = int(m.group(1)) + 40 * int(m.group(2) or 0)
        return "blitz" if total < 600 else "rapid" if total < 3600 else "classical"
    return "classical"


def load_games(data: dict) -> list:
    games, seq = [], 0
    for ri, rnd in enumerate(data.get("rounds", [])):
        try:
            text = _get(f"{API}/broadcast/round/{rnd['id']}.pgn").text
        except requests.HTTPError as e:
            print(f"Runda {rnd.get('name')}: {e}")
            continue
        fh = io.StringIO(text)
        while (g := chess.pgn.read_game(fh)) is not None:
            h = g.headers
            res = h.get("Result", "*")
            if res not in ("1-0", "0-1", "1/2-1/2") or not list(g.mainline_moves()):
                continue  # trwające albo puste
            games.append(G(seq, ri, rnd.get("name", f"{ri + 1}"), g, norm_name(h.get("White")), norm_name(h.get("Black")),
                           res, _tc(g, rnd.get("name", "")),
                           (int(h.get("WhiteElo") or 0), int(h.get("BlackElo") or 0)),
                           (h.get("WhiteFideId", ""), h.get("BlackFideId", ""))))
            seq += 1
    return games


# ---------------------------------------------------------------- struktura turnieju
def is_knockout(games: list) -> bool:
    if os.environ.get("NEWS_FORMAT") in ("ko", "rr"):
        return os.environ["NEWS_FORMAT"] == "ko"
    players = {p for g in games for p in (g.white, g.black)}
    if len(players) < 4:
        return False
    opp = {p: set() for p in players}
    for g in games:
        opp[g.white].add(g.black)
        opp[g.black].add(g.white)
    pairs = {g.pair for g in games}
    return max(len(o) for o in opp.values()) <= math.log2(len(players)) and len(games) / len(pairs) >= 2


@dataclass
class Match:
    a: str
    b: str
    games: list
    stage: int = 1
    third: bool = False

    def score(self, before_seq: int | None = None) -> tuple:
        gs = [g for g in self.games if before_seq is None or g.seq < before_seq]
        return sum(g.points(self.a) for g in gs), sum(g.points(self.b) for g in gs)

    def finished_before(self, seq: int) -> bool:
        return max(g.seq for g in self.games) < seq

    next_players: set = field(default_factory=set)  # gracze meczów kolejnego etapu (bez meczu o 3. miejsce)

    @property
    def mixed(self) -> bool:
        """Różne tempa w meczu (klasyczne/rapid/blitz) — punkty organizatora bywają ważone, więc nie sumujemy."""
        return len({g.tc for g in self.games}) > 1

    def winner(self) -> str | None:
        for p in (self.a, self.b):  # kto gra w następnym etapie — ten wygrał mecz (niezależnie od punktacji)
            if p in self.next_players and not ({self.a, self.b} <= self.next_players):
                return p
        if self.mixed:  # ostatni etap z mieszanym tempem: nie zgadujemy punktacji organizatora
            return None
        sa, sb = self.score()
        return self.a if sa > sb else self.b if sb > sa else None


THIRD_RE = re.compile(r"3rd|third|bronze|place|platz|miejsce", re.I)


def knockout(games: list) -> list:
    by_pair = {}
    for g in games:
        by_pair.setdefault(g.pair, []).append(g)
    matches = sorted((Match(*sorted(p), gs) for p, gs in by_pair.items()), key=lambda m: m.games[0].seq)
    played = {}
    for m in matches:  # etap = liczba wcześniej rozegranych meczów gracza + 1
        m.stage = max(played.get(m.a, 0), played.get(m.b, 0)) + 1
        played[m.a] = played[m.b] = m.stage
    last = max(m.stage for m in matches)
    final_stage = [m for m in matches if m.stage == last]
    if len(final_stage) == 2:  # finał + mecz o 3. miejsce: najpierw po nazwie rundy, potem po wynikach półfinałów
        named = [m for m in final_stage if any(THIRD_RE.search(g.round_name) for g in m.games)]
        if len(named) == 1:
            named[0].third = True
        else:
            semis = [m for m in matches if m.stage == last - 1]
            losers = set()
            for m in semis:
                sa, sb = m.score()
                if sa != sb:
                    losers.add(m.b if sa > sb else m.a)
            for m in final_stage:
                if {m.a, m.b} <= losers:
                    m.third = True
    for m in matches:  # zwycięzca = kto gra w głównym meczu następnego etapu
        m.next_players = {p for x in matches if x.stage == m.stage + 1 and not x.third for p in (x.a, x.b)}
    return matches


def stage_name(m: Match, matches: list) -> str:
    if m.third:
        return L.t["third"]
    left = sum(1 for x in matches if x.stage == m.stage and not x.third)
    return L.t["stage"].get(left, L.t["round_n"].format(n=m.stage))


def standings(games: list, before_seq: int) -> list:
    pts = {}
    for g in games:
        for p in (g.white, g.black):
            pts.setdefault(p, 0.0)
        if g.seq < before_seq:
            pts[g.white] += g.points(g.white)
            pts[g.black] += g.points(g.black)
    return sorted(pts.items(), key=lambda kv: -kv[1])


# ---------------------------------------------------------------- wybór partii
def _evals(game: chess.pgn.Game, eng) -> list:
    out, board = [], game.board()
    for mv in game.mainline_moves():
        board.push(mv)
        if board.is_game_over():
            out.append(1000 if board.is_checkmate() and board.turn == chess.BLACK else
                       -1000 if board.is_checkmate() else 0)
            continue
        s = eng.analyse(board, chess.engine.Limit(depth=int(os.environ.get("NEWS_DEPTH", "11"))))["score"].white()
        out.append(max(-1000, min(1000, s.score(mate_score=1000))))
    return out


def reddit_mentions(g: G) -> int:
    """Wzmianki na r/chess z ostatnich dni (proxy 'o czym się mówi'). Brak odpowiedzi = 0."""
    q = f'"{g.white.split()[-1]}" "{g.black.split()[-1]}"'
    try:
        r = requests.get("https://www.reddit.com/r/chess/search.json",
                         params={"q": q, "restrict_sr": 1, "t": "month", "limit": 50},
                         headers={"User-Agent": UA["User-Agent"]}, timeout=20)
        if r.ok:
            return sum(int(c["data"].get("num_comments", 0)) + 1 for c in r.json()["data"]["children"])
    except Exception:  # noqa: BLE001 — Reddit bywa niedostępny z chmury
        pass
    return -1


def score_games(games: list, matches: list | None, engine_path: str | None) -> list:
    n_rounds = max(g.round_idx for g in games) + 1
    top = sorted({e for g in games for e in g.elo if e}, reverse=True)[:3]
    by_match = {}
    if matches:
        for m in matches:
            for g in m.games:
                by_match[g.seq] = m
    eng = chess.engine.SimpleEngine.popen_uci(engine_path) if engine_path else None
    reddit = {}
    try:
        for g in games:
            w = []
            if matches:
                m = by_match[g.seq]
                last = max(x.stage for x in matches)
                stage_w = 1.2 if m.third else {0: 3.0, 1: 2.0, 2: 1.4}.get(last - m.stage, 1.0)
                w.append(f"etap×{stage_w}")
            else:
                stage_w = 1.0 + g.round_idx / max(1, n_rounds - 1)
                w.append(f"runda×{stage_w:.1f}")
            tc_w = TC_WEIGHT[g.tc]
            base = (2.0 if g.result != "1/2-1/2" else 0.8) * stage_w * tc_w
            avg = sum(g.elo) / 2 if all(g.elo) else 2600
            elo_b = max(0.0, min(3.0, (avg - 2600) / 100)) * 0.5
            star = 0.5 if any(e in top for e in g.elo) else 0.0
            drama = 0.0
            if eng:
                ev = _evals(g.game, eng)
                swing = max((abs(b - a) for a, b in zip(ev, ev[1:])), default=0)
                flips = sum(1 for a, b in zip(ev, ev[1:]) if a * b < 0 and max(abs(a), abs(b)) > 100)
                drama = min(2.0, swing / 300) + 0.3 * min(flips, 4)
                w.append(f"dramat {drama:.1f}")
            decider = 0.0
            if matches:
                m = by_match[g.seq]
                win = m.winner()
                decisive = [x for x in m.games if x.result != "1/2-1/2" and win and x.points(win) == 1]
                if decisive and g is decisive[-1]:
                    decider = 1.5
                    w.append("rozstrzyga mecz")
            key = (g.white, g.black)
            if key not in reddit and len(reddit) < 25:
                reddit[key] = reddit_mentions(g)
            buzz = math.log1p(max(0, reddit.get(key, 0))) * 0.4
            if reddit.get(key, -1) > 0:
                w.append(f"reddit {reddit[key]}")
            g.score = round(base + elo_b + star + drama + decider + buzz, 2)
            g.why = [g.tc, g.result] + w
    finally:
        if eng:
            eng.quit()
    return sorted(games, key=lambda x: -x.score)


# ---------------------------------------------------------------- zapis i potok
def write_pgn(g: G, path: Path) -> None:
    h = g.game.headers
    h["White"], h["Black"] = g.white, g.black
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(str(g.game) + "\n", encoding="utf-8")


def photos_for(games: list) -> dict:
    """Portrety wszystkich uczestników po FIDE ID (Wikidata P1440). Zwraca {nazwa_z_PGN: nazwa_do_wyświetlenia}."""
    from fetch_portraits import person_by_fide, save_photo

    fides = {}
    for g in games:
        for name, fid in ((g.white, g.fide[0]), (g.black, g.fide[1])):
            if fid and name not in fides:
                fides[name] = fid
    names = {}
    for name in sorted({p for g in games for p in (g.white, g.black)}):
        names[name] = name
        fid = fides.get(name)
        if not fid:
            print(f"Portret {name}: brak FIDE ID")
            continue
        try:
            person = person_by_fide(fid)
            if not person:
                print(f"Portret {name}: brak w Wikidata (FIDE {fid})")
                continue
            label = (person.get("labels", {}).get("en") or {}).get("value") or name
            names[name] = label
            import countries
            from fetch_portraits import WD_API, api
            countries.remember(label, person, api, WD_API)
            print(f"Portret {label}: {save_photo(label, person, f'FIDE {fid}')}")
        except requests.RequestException as e:
            print(f"Portret {name}: błąd sieci {e.__class__.__name__}")
    return names


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tournament", required=True)
    ap.add_argument("--test", action="store_true", help="paczka testowa (tag news-test-…), bez wpisu w harmonogramie")
    ap.add_argument("--select-only", action="store_true")
    ap.add_argument("--dry-tts", action="store_true")
    args = ap.parse_args()

    data = find_tour(args.tournament)
    tour = data["tour"]
    print(f"Turniej: {tour.get('name')} ({tour.get('id')}), rund: {len(data.get('rounds', []))}")
    games = load_games(data)
    if not games:
        raise SystemExit("Brak zakończonych partii")
    ko = is_knockout(games)
    matches = knockout(games) if ko else None
    print(f"Format: {'nokaut' if ko else 'kołowy'}; partii: {len(games)}")
    if matches:
        for m in matches:
            print(f"  etap {m.stage}{' (3. miejsce)' if m.third else ''}: {m.a} – {m.b} {m.score()} -> {m.winner()}")
    ranked = score_games(games, matches, os.environ.get("STOCKFISH_PATH") or "/usr/games/stockfish")
    names = photos_for(games if (matches or len({p for g in games for p in (g.white, g.black)}) <= 12)
                       else [g for g in ranked[:20]])
    import countries
    year_now = datetime.now(timezone.utc).year
    for g in ranked:  # "swój" gracz: Polak na kanale polskim, Niemiec na niemieckim
        home = [p for p in (g.white, g.black) if countries.country(names.get(p, p), year_now) == L.code]
        if home:
            g.score = round(g.score + HOME_BONUS, 2)
            g.why.append(f"swój gracz: {', '.join(home)}")
    ranked.sort(key=lambda x: -x.score)
    for g in ranked[:8]:
        print(f"  {g.score:5.2f}  {g.round_name}: {g.white} – {g.black} {g.result}  {g.why}")
    if args.select_only:
        return 0

    pick = ranked[0]
    year = int((pick.game.headers.get("Date") or "")[:4] or datetime.now(timezone.utc).year)
    gid = f"news_{slug(tour.get('name', 'turniej'))[:40]}_{slug(pick.white.split()[-1])}_{slug(pick.black.split()[-1])}_{pick.seq}"
    pgn_path = ROOT / "games" / "news" / f"{gid}.pgn"
    for old, new in names.items():  # nazwisko z FIDE zostaje przy nowej nazwie z Wikidata
        if old in SURNAMES:
            SURNAMES[new] = SURNAMES[old]
    for gg in games:  # nazwy z Wikidata (np. "Rameshbabu Praggnanandhaa") — w PGN, drabince i faktach
        gg.white, gg.black = names.get(gg.white, gg.white), names.get(gg.black, gg.black)
    write_pgn(pick, pgn_path)

    # stan turnieju PRZED partią — do planszy i do faktów
    for m in matches or []:
        m.a, m.b = names.get(m.a, m.a), names.get(m.b, m.b)
    facts = [f"Turniej: {tour.get('name')}", f"Runda w transmisji: {pick.round_name}",
             f"Data: {pick.game.headers.get('Date', '?')}", f"Miejsce: {pick.game.headers.get('Site', '?')}",
             f"Tempo gry: {pick.tc}",
             f"Rankingi: {pick.white} {pick.elo[0] or '?'}, {pick.black} {pick.elo[1] or '?'}"]
    label = re.sub(rf"(^\s*{year}\s+|\s+{year}\s*$)", "", tour.get("name", "")).strip()  # rok jest w kadrze osobno
    if matches:
        m = next(x for x in matches if pick in x.games)
        sname = stage_name(m, matches)
        facts += ["Format: turniej pucharowy (mecze)", f"Etap: {sname}"]
        if m.mixed:  # punktacja organizatora może ważyć partie — podajemy tylko wyniki partii, bez sumy
            earlier = [g for g in m.games if g.seq < pick.seq]
            facts.append("Mecz składa się z partii w różnym tempie; organizator może liczyć punkty inaczej — "
                         "NIE podawaj łącznego wyniku meczu.")
            facts.append("Wcześniejsze partie tego meczu: " + ("; ".join(
                f"{g.round_name}: {g.white} – {g.black} {g.result}" for g in earlier) or "brak (to pierwsza partia)"))
        else:
            sa, sb = m.score(pick.seq)
            facts += [f"Stan meczu {m.a} – {m.b} przed tą partią: {sa:g}–{sb:g}",
                      f"Stan meczu po tej partii: {m.score(pick.seq + 1)[0]:g}–{m.score(pick.seq + 1)[1]:g}"]
        if "rozstrzyga mecz" in pick.why:
            facts.append(f"Ta partia rozstrzygnęła mecz na korzyść: {m.winner()}")
        label = f"{label} · {sname}"
    else:
        table = standings(games, pick.seq)
        facts += ["Format: turniej kołowy", "Tabela przed tą partią: " + ", ".join(f"{p} {s:g}" for p, s in table[:8])]
        label = f"{label} · {pick.round_name}"
    facts.append("To jest odcinek o partii z bieżącego turnieju (nowości ze świata szachów). "
                 "Na początku krótko wyjaśnij stawkę: etap, stan meczu albo tabeli. Nie dopowiadaj nic spoza tych faktów.")
    (ROOT / "facts").mkdir(exist_ok=True)
    (ROOT / "facts" / f"{gid}.md").write_text("\n".join(facts) + "\n", encoding="utf-8")

    entry = {"id": gid, "white": pick.white, "black": pick.black, "year": year, "result": pick.result,
             "white_last": surname(pick.white), "black_last": surname(pick.black),
             "white_first": pick.white.replace(surname(pick.white), "").strip(),
             "black_first": pick.black.replace(surname(pick.black), "").strip(),
             "site": pick.game.headers.get("Site"), "event": tour.get("name"), "label": label,
             "news": True, "lichess_tour": tour.get("id"), "pgn_verified": False}
    cat = json.loads(NEWS.read_text(encoding="utf-8")) if NEWS.exists() else {"games": []}
    cat["games"] = [x for x in cat["games"] if x["id"] != gid] + [entry]
    NEWS.write_text(json.dumps(cat, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    from bracket import draw_bracket, draw_table
    pre = L.out / f"{gid}_preroll.png"
    pre.parent.mkdir(parents=True, exist_ok=True)
    if matches:
        draw_bracket(tour.get("name", ""), year, matches, pick, pre)
    else:
        draw_table(tour.get("name", ""), year, standings(games, pick.seq), pick, pre)

    py = sys.executable
    script = L.scripts / f"{gid}.json"
    video = L.out / f"{gid}.mp4"
    if not script.exists():
        subprocess.run([py, str(SRC / "script_gen.py"), "--pgn", str(pgn_path), "--out", str(script), "--name", gid],
                       check=True, cwd=ROOT)
    subprocess.run([py, str(SRC / "main.py"), "--pgn", str(pgn_path), "--script", str(script), "--out", str(video),
                    "--preroll", str(pre)] + (["--dry-run"] if args.dry_tts else []), check=True, cwd=ROOT)

    import scheduler as S
    sc = json.loads(script.read_text(encoding="utf-8"))
    title, description, tags = S.describe(entry, sc, pgn_path, json.loads(video.with_suffix(".timing.json").read_text()))
    tags = [t for t in tags if t not in L.t["tags"][3:]] + L.t["news_tags"]
    description = description.replace(L.t["hashtags"], L.t["news_hashtags"])
    when = "одразу (новина)" if not args.test else "ТЕСТ — новина, публікація на ваш розсуд"
    tag = f"{L.tag_prefix}news{'-test' if args.test else ''}-{gid}"[:120]
    info = S.deliver_package(entry, pgn_path, video, title, description, tags, when, 0,
                             remote=not args.dry_tts, tag=tag, badge=label, preroll=pre)
    print("Paczka:", info)
    return 0


if __name__ == "__main__":
    sys.exit(main())
