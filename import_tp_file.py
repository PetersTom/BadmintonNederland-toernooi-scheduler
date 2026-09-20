import sys
import pyodbc
from collections import defaultdict
from datetime import datetime, time, date, timedelta, timezone
import pandas as pd

ACCESS_DRIVER = "{Microsoft Access Driver (*.mdb, *.accdb)}"
PASSWORD = "d4R2GY76w2qzZ"

CET = timezone(timedelta(hours=1))
CEST = timezone(timedelta(hours=2))

def nl_timezone(d):
    """CET/CEST offset for a date in the Netherlands (EU-summertime)."""
    if _last_sunday(d.year, 3) <= d < _last_sunday(d.year, 10):
        return CEST
    return CET

def _last_sunday(year, month):
    """Function to determine the last sunday of a month. Used to determine timezone"""
    d = date(year, month, 31)
    return d - timedelta(days=(d.weekday() - 6) % 7)

def combine_full_name(firstname, middlename, name):
    parts = [p.strip() for p in (firstname, middlename, name) if p and p.strip()]
    return " ".join(parts) if parts else "(onbekend)"

def onderdeel_type(gender, eventtype):
    """Leid het onderdeel-type (HE/HD/VE/VD/GD) af uit gender + eventtype.

    gender:    1=heren, 2=dames, 3=gemengd
    eventtype: 1=enkel, 2=dubbel

    This is the `.mdb` exporter's original int-coded derivation (from the
    Access `Event` table's `gender`/`eventtype` columns). For the web
    scraper's letter-coded event names ("HE1", "DE4", ...), see
    `onderdeel_type_from_site` below.
    """
    if gender == 3:
        return "GD"
    if gender == 1:
        return "HE" if eventtype == 1 else "HD"
    if gender == 2:
        return "DE" if eventtype == 1 else "DD"
    # Onbekend geslacht: val terug op iets dat het schema accepteert.
    return "HE" if eventtype == 1 else "HD"

_KO_RONDE_NAMEN = {
    1: "finale",
    2: "halve finale",
    3: "kwartfinale",
    4: "achtste finale",
    5: "zestiende finale",
    6: "tweeendertigste finale",
    7: "vierenzestigste finale",
}

def sid(x):
    """Convert an id to a string in the easiest way possible"""
    return str(x)

def knockout_ronde(depth):
    """Naam van een knock-out ronde op basis van de diepte tot de finale.

    `depth` is de afstand-tot-finale: 1 = finale, 2 = halve finale, etc.
    """
    if depth in _KO_RONDE_NAMEN:
        return _KO_RONDE_NAMEN[depth]
    return f"ronde van {2 ** depth}"

def is_null_date(dt):
    """Access uses 30-12-1899 als 'empty' date instead of NULL."""
    return dt is None or (dt.year <= 1899)

def connect(path, password):
    conn_str = f"DRIVER={ACCESS_DRIVER};DBQ={path};"
    if password:
        conn_str += f"PWD={password};"
    return pyodbc.connect(conn_str)

def fetch_all(cur, sql):
    cur.execute(sql)
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, row)) for row in cur.fetchall()]

def extract_spelers(cur):
    rows = fetch_all(
        cur, "SELECT id, name, firstname, middlename, dob FROM Player ORDER BY id"
    )
    spelers = []
    for r in rows:
        speler = {
            "id": sid(r["id"]),
            "firstname": r["firstname"],
            "middlename": r["middlename"] if r["middlename"] is not None else "",
            "lastname": r["name"],
        }
        if not is_null_date(r["dob"]):
            speler["birth_date"] = r["dob"].date().isoformat()
        else:
            speler["birth_date"] = ""
        spelers.append(speler)
    return spelers

def extract_onderdelen(cur):
    rows = fetch_all(
        cur, "SELECT id, gender, eventtype, [level] FROM Event ORDER BY id"
    )
    onderdelen = []
    for r in rows:
        niveau = r["level"] if r["level"] and r["level"] >= 1 else 1
        onderdelen.append(
            {
                "id": sid(r["id"]),
                "type": onderdeel_type(r["gender"], r["eventtype"]),
                "level": int(niveau),
            }
        )
    return onderdelen


def extract_tijdsloten(cur):
    # TournamentTime.tournamentday bevat de datum van de speeldag; tournamenttime
    # bevat de tijd-op-de-dag (met Access' nuldatum 30-12-1899 als datumdeel).
    rows = fetch_all(
        cur,
        "SELECT id, tournamenttime, tournamentday, indexnr, courts "
        "FROM TournamentTime ORDER BY tournamentday, indexnr",
    )
    tijdsloten = []
    for r in rows:
        courts = r["courts"] or 0
        t = r["tournamenttime"]
        day = r["tournamentday"]
        # Sloten zonder banen, zonder tijd of zonder dag overslaan.
        if courts < 1 or t is None or day is None:
            continue
        tod = t.time() if isinstance(t, datetime) else t
        # Access-nul (00:00) betekent 'geen tijd ingevuld' -> geen echt slot.
        if tod == time(0, 0, 0):
            continue
        day = day.date() if isinstance(day, datetime) else day
        start = datetime.combine(day, tod, tzinfo=nl_timezone(day))
        tijdsloten.append(
            {
                "id": sid(r["id"]),
                "start_time": start.isoformat(),
                "court_count": int(courts),
            }
        )
    return tijdsloten

def _is_placement(row):
    """Plaatsingsrij (blad): geen kinderen."""
    return (row["van1"] or 0) == 0 and (row["van2"] or 0) == 0


def extract_wedstrijden(cur):
    matches = fetch_all(
        cur,
        "SELECT id, event, draw, roundnr, entry, link, van1, van2, planning "
        "FROM PlayerMatch",
    )
    draws = fetch_all(cur, "SELECT id, event, drawtype, name FROM Draw")
    entries = fetch_all(cur, "SELECT id, player1, player2 FROM Entry")
    links = fetch_all(cur, "SELECT id, src_draw, src_pos FROM Link")

    draw_meta = {d["id"]: d for d in draws}
    link_src_draw = {l["id"]: l["src_draw"] for l in links}

    entry_players = {}
    for e in entries:
        players = [p for p in (e["player1"], e["player2"]) if p]
        entry_players[e["id"]] = [sid(p) for p in players]

    # code_map[draw][planning] -> rij; en per draw alle rijen.
    code_map = defaultdict(dict)
    rows_by_draw = defaultdict(list)
    for m in matches:
        rows_by_draw[m["draw"]].append(m)
        code = m["planning"]
        if code is not None:
            code_map[m["draw"]][code] = m

    def occupied(draw, code, seen=None):
        """Levert deze knoop uiteindelijk een deelnemer op (geen lege bye-tak)?"""
        node = code_map[draw].get(code)
        if node is None:
            return False
        if _is_placement(node):
            return bool(node["entry"]) or bool(node["link"])
        if seen is None:
            seen = set()
        if code in seen:
            return False
        seen.add(code)
        return occupied(draw, node["van1"], seen) or occupied(draw, node["van2"], seen)

    def is_real_match(node):
        """Een echt te spelen wedstrijdknoop: beide zijden zijn bezet."""
        return (
            not _is_placement(node)
            and occupied(node["draw"], node["van1"])
            and occupied(node["draw"], node["van2"])
        )

    # --- Pass A: bepaal alle echte wedstrijden en hun geexporteerde id ---------
    # Poules slaan elke paring dubbel op (spiegel); dedup op {van1, van2}.
    pair_to_id = {}                       # (draw, frozenset) -> geexporteerde id (str)
    matchids_by_draw = defaultdict(list)  # draw -> [geexporteerde ids]
    exported = []                         # lijst van (node) canonieke rijen

    seen_pairs = set()
    for draw in sorted(rows_by_draw):
        for node in sorted(rows_by_draw[draw], key=lambda r: r["id"]):
            if not is_real_match(node):
                continue
            pair = (draw, frozenset((node["van1"], node["van2"])))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            eid = sid(node["id"])
            pair_to_id[pair] = eid
            matchids_by_draw[draw].append(eid)
            exported.append(node)

    def exported_id_of(node):
        return pair_to_id[(node["draw"], frozenset((node["van1"], node["van2"])))]

    # --- Pass B: los per zijde het team en de prerequisites op -----------------
    def resolve_side(draw, code, seen=None):
        """(team_or_None, set_match_prereq_ids, set_src_draws)."""
        node = code_map[draw].get(code)
        if node is None:
            return None, set(), set()
        if _is_placement(node):
            # Afhankelijk van een ander schema (poule -> hoofdschema): deelnemer
            # onbekend, het bronschema is de prerequisite. Link heeft voorrang op
            # een reeds ingevulde entry, zodat de export losstaat van de uitslag.
            if node["link"] and node["link"] in link_src_draw:
                return None, set(), {link_src_draw[node["link"]]}
            if node["entry"]:
                return list(entry_players.get(node["entry"], [])), set(), set()
            return None, set(), set()  # lege plaatsing (bye-zijde)
        # Wedstrijdknoop.
        if is_real_match(node):
            return None, {exported_id_of(node)}, set()
        # Bye-knoop: precies een tak is bezet -> daar doorheen zakken.
        if seen is None:
            seen = set()
        if code in seen:
            return None, set(), set()
        seen.add(code)
        for v in (node["van1"], node["van2"]):
            if occupied(draw, v):
                return resolve_side(draw, v, seen)
        return None, set(), set()

    wedstrijden = []
    for node in exported:
        draw = node["draw"]
        meta = draw_meta.get(draw, {})
        team_a, pre_m_a, pre_d_a = resolve_side(draw, node["van1"])
        team_b, pre_m_b, pre_d_b = resolve_side(draw, node["van2"])

        prereqs = set(pre_m_a) | set(pre_m_b)
        for src_draw in (pre_d_a | pre_d_b):
            prereqs.update(matchids_by_draw.get(src_draw, []))
        prereqs.discard(sid(node["id"]))  # nooit naar zichzelf verwijzen

        if meta.get("drawtype") == 1:
            ronde = knockout_ronde(node["planning"] // 1000)
        else:
            ronde = meta.get("name") or "poule"

        wedstrijd = {
            "id": sid(node["id"]),
            "event_id": sid(node["event"]),
            "round": ronde,
            "roundnr": node["roundnr"],
            "team_a": team_a or [],
            "team_b": team_b or [],
        }
        if prereqs:
            wedstrijd["prerequisites"] = sorted(prereqs, key=lambda x: int(x))
        else:
            wedstrijd["prerequisites"] = ""
        wedstrijden.append(wedstrijd)

    wedstrijden.sort(key=lambda w: int(w["id"]))
    return wedstrijden


def build_sourcedata(conn):
    cur = conn.cursor()
    data = {
        "players": pd.DataFrame(extract_spelers(cur)),
        "events":pd.DataFrame(extract_onderdelen(cur)),
        "matches": pd.DataFrame(extract_wedstrijden(cur)),
        "time_slots": pd.DataFrame(extract_tijdsloten(cur)),
    }
    # insert the event into the matches
    data["matches"] = data["matches"].merge(data["events"][["id", "type", "level"]], left_on='event_id', right_on='id', how="left")
    # combine the columns and remove the old ones
    data['matches']['event'] = data['matches']['type'] + data['matches']['level'].astype(str)
    data['matches'] = data['matches'].drop(columns=['level', 'type', 'id_y']) # id_y is the old id from events
    data['matches'] = data['matches'].rename(columns={'id_x': 'id'})
    # move the new column to the right place
    event_col = data['matches'].pop('event')
    data['matches'].insert(2, 'event', event_col)

    # Add planned timeslot id to matches
    data['matches']['timeslot_id'] = None
    # Add planned matches to each timeslot
    data['time_slots']['matches'] = [[] for _ in range(len(data['time_slots']))]

    # Add the number of rounds to the events database
    def get_round_count(group):
        # it is a group if it starts with "Groep" or if there is only a single poule and it starts with the eventname
        is_groep = group["round"].str.startswith("Groep", na=False) | group['round'].str.startswith(group['event'].iloc[0], na=False)

        # Every other unique round = 1
        other_count = group.loc[~is_groep, "round"].nunique()

        # All Groep rounds together = highest roundnr for this event
        groep_count = group.loc[is_groep, "roundnr"].max()
        groep_count = 0 if pd.isna(groep_count) else groep_count

        return groep_count + other_count


    round_counts = (
        data["matches"]
        .groupby("event_id")
        .apply(get_round_count)
    )

    data["events"]["rounds"] = (
        data["events"]["id"]
        .map(round_counts)
        .fillna(0)
        .astype(int)
    )

    return data


def read_database(database_path):
    """
    Produces a dict containing the "players", "events", "matches", and "time_slots" in the .TP file
    """
    try:
        conn = connect(database_path, PASSWORD)
    except pyodbc.Error as exc:
        print(f"Could not get a connection to the TP database: {exc}", file=sys.stderr)
        return 1
    try:
        data = build_sourcedata(conn)
        return data
    finally:
        conn.close()