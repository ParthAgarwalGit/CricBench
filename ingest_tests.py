"""
ingest_tests.py
---------------
Ingests Cricsheet Test match JSON files (tests_json.zip or a directory of
.json files) into a SQLite database using schema_tests.sql.

Usage:
    python ingest_tests.py

Paths are configured in the Configuration section below.
"""

import os
import json
import zipfile
import sqlite3
import logging
import time

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
DB_PATH     = os.path.join(BASE_DIR, 'tests.db')
SCHEMA_PATH = os.path.join(BASE_DIR, 'schema_tests.sql')
LOG_PATH    = os.path.join(BASE_DIR, 'ingestion_tests.log')

# Source: either a zip file OR a directory of .json files.
# The script will prefer the zip if it exists.
JSON_ZIP_PATH = os.path.join(BASE_DIR, 'tests_json.zip')
JSON_DIR_PATH = os.path.join(BASE_DIR, 'tests_json')       # fallback directory

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    filename=LOG_PATH,
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    filemode='w'
)


# ---------------------------------------------------------------------------
# Database setup
# ---------------------------------------------------------------------------
def create_database():
    """Reads schema_tests.sql and (re)creates the database."""
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    print(f"Creating database at {DB_PATH} ...")
    with open(SCHEMA_PATH, 'r') as f:
        schema = f.read()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(schema)
    conn.commit()
    conn.close()
    print("Database created successfully.")


# ---------------------------------------------------------------------------
# Core processing
# ---------------------------------------------------------------------------
def process_file(db_conn, file_content: bytes, filename: str):
    """
    Parses a single JSON file (as bytes) and inserts all records into the DB.
    Raises on unrecoverable errors so the caller can skip the file.
    """
    cursor = db_conn.cursor()
    match_id = int(os.path.splitext(filename)[0])
    logging.info(f"--- Processing {filename} ---")

    data = json.loads(file_content)
    info = data.get('info', {})

    # -----------------------------------------------------------------------
    # Build player registry for this file
    # -----------------------------------------------------------------------
    player_registry_raw = info.get('registry', {}).get('people', {})
    if not player_registry_raw:
        raise ValueError(f"No registry.people in {filename}")

    registry = {
        name.strip(): pid
        for name, pid in player_registry_raw.items()
        if name and pid
    }

    # Upsert all players found in this file
    cursor.executemany(
        "INSERT OR IGNORE INTO Players (player_id, player_name) VALUES (?, ?)",
        [(pid, name) for name, pid in registry.items()]
    )

    def pid(name):
        """Resolve common name -> player_id via the file's registry."""
        if not name or not isinstance(name, str):
            return None
        return registry.get(name.strip())

    # -----------------------------------------------------------------------
    # Matches
    # -----------------------------------------------------------------------
    dates       = info.get('dates', [''])
    start_date  = dates[0] if dates else ''
    end_date    = dates[-1] if len(dates) > 1 else None

    outcome     = info.get('outcome', {})
    winner      = outcome.get('winner')                         # None → draw/no result

    by          = outcome.get('by', {})
    if by:
        result_type   = list(by.keys())[0]                     # 'runs' or 'wickets'
        result_margin = list(by.values())[0]
    else:
        # 'draw', 'tie', 'no result', etc.
        result_type   = outcome.get('result', 'no result')
        result_margin = None

    event           = info.get('event', {})
    series_name     = event.get('name')
    match_type_num  = event.get('match_number')

    officials       = info.get('officials', {})
    umpires         = officials.get('umpires', [])
    tv_umpire_list  = officials.get('tv_umpires', [])
    referee_list    = officials.get('match_referees', [])

    pom_name = (info.get('player_of_match') or [None])[0]
    pom_id   = pid(pom_name) if pom_name else None

    teams = info.get('teams', ['', ''])

    cursor.execute("""
        INSERT INTO Matches (
            match_id, season, start_date, end_date, venue, city,
            series_name, match_type_number, gender, team_type,
            team1, team2,
            toss_winner, toss_decision,
            match_winner, result_type, result_margin,
            player_of_match_id,
            umpire1, umpire2, tv_umpire, match_referee
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        match_id,
        str(info.get('season', '')),
        start_date, end_date,
        info.get('venue', 'Unknown'),
        info.get('city'),
        series_name, match_type_num,
        info.get('gender'),
        info.get('team_type'),
        teams[0] if len(teams) > 0 else '',
        teams[1] if len(teams) > 1 else '',
        info.get('toss', {}).get('winner', 'Unknown'),
        info.get('toss', {}).get('decision', 'Unknown'),
        winner, result_type, result_margin,
        pom_id,
        umpires[0] if len(umpires) > 0 else None,
        umpires[1] if len(umpires) > 1 else None,
        tv_umpire_list[0] if tv_umpire_list else None,
        referee_list[0]   if referee_list   else None,
    ))

    # -----------------------------------------------------------------------
    # PlayerInMatch
    # -----------------------------------------------------------------------
    pim_rows = []
    for team_name, player_list in info.get('players', {}).items():
        for common_name in player_list:
            player_id = pid(common_name)
            if player_id:
                pim_rows.append((match_id, player_id, team_name))
            else:
                logging.warning(
                    f"{filename}: player '{common_name}' not in registry — "
                    f"skipping PlayerInMatch row."
                )
    if pim_rows:
        cursor.executemany(
            "INSERT OR IGNORE INTO PlayerInMatch (match_id, player_id, team_name) "
            "VALUES (?, ?, ?)",
            pim_rows
        )

    # -----------------------------------------------------------------------
    # Deliveries + FielderDismissals
    # -----------------------------------------------------------------------
    for inning_idx, inning_data in enumerate(data.get('innings', [])):
        inning_number = inning_idx + 1          # 1–4 for Tests; no super-overs

        batting_team = inning_data.get('team')
        bowling_team = next(
            (t for t in teams if t != batting_team),
            'Unknown'
        )

        for over_data in inning_data.get('overs', []):
            over_num = over_data.get('over')
            legal_ball_count = 0

            for seq_idx, delivery in enumerate(over_data.get('deliveries', [])):
                extras_info = delivery.get('extras', {})
                wides   = extras_info.get('wides',   0)
                noballs = extras_info.get('noballs',  0)
                byes    = extras_info.get('byes',     0)
                legbyes = extras_info.get('legbyes',  0)

                # Only count legal deliveries towards ball_number
                if wides == 0 and noballs == 0:
                    legal_ball_count += 1
                ball_number = legal_ball_count

                striker_id    = pid(delivery.get('batter'))
                non_striker_id = pid(delivery.get('non_striker'))
                bowler_id     = pid(delivery.get('bowler'))

                if not all([striker_id, non_striker_id, bowler_id]):
                    missing = []
                    if not striker_id:     missing.append(f"batter:'{delivery.get('batter')}'")
                    if not non_striker_id: missing.append(f"non_striker:'{delivery.get('non_striker')}'")
                    if not bowler_id:      missing.append(f"bowler:'{delivery.get('bowler')}'")
                    logging.warning(
                        f"{filename} inn={inning_number} O{over_num} ball{seq_idx+1}: "
                        f"ID lookup failed for {', '.join(missing)} — skipping delivery."
                    )
                    continue

                wicket_list  = delivery.get('wickets') or []
                wicket_info  = wicket_list[0] if wicket_list else {}
                player_out   = wicket_info.get('player_out')
                player_out_id = pid(player_out) if player_out else None
                fielder_names = [
                    f.get('name') for f in wicket_info.get('fielders', [])
                    if f.get('name')
                ]
                fielder_ids   = [pid(n) for n in fielder_names if pid(n)]

                if player_out and not player_out_id:
                    logging.warning(
                        f"{filename}: player_out '{player_out}' ID not found — "
                        f"stored as NULL."
                    )
                if len(fielder_names) != len(fielder_ids):
                    failed = [n for n in fielder_names if not pid(n)]
                    logging.warning(
                        f"{filename}: fielder ID lookup failed for {failed}."
                    )

                try:
                    cursor.execute("""
                        INSERT INTO Deliveries (
                            match_id, inning, over_number, ball_number,
                            batting_team, bowling_team,
                            striker_id, non_striker_id, bowler_id,
                            runs_scored, extra_runs,
                            wides, noballs, byes, legbyes,
                            wicket_type, player_out_id
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        match_id, inning_number, over_num, ball_number,
                        batting_team, bowling_team,
                        striker_id, non_striker_id, bowler_id,
                        delivery.get('runs', {}).get('batter', 0),
                        delivery.get('runs', {}).get('extras', 0),
                        wides, noballs, byes, legbyes,
                        wicket_info.get('kind'),
                        player_out_id,
                    ))

                    if fielder_ids:
                        delivery_id = cursor.lastrowid
                        cursor.executemany(
                            "INSERT INTO FielderDismissals "
                            "(delivery_id, fielder_id) VALUES (?, ?)",
                            [(delivery_id, fid) for fid in fielder_ids]
                        )

                except sqlite3.IntegrityError as e:
                    logging.error(
                        f"{filename} inn={inning_number} O{over_num} "
                        f"B{ball_number}: IntegrityError — {e} — skipping."
                    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main():
    create_database()
    start_time = time.time()

    # ------------------------------------------------------------------
    # Determine source: zip or directory
    # ------------------------------------------------------------------
    use_zip = os.path.exists(JSON_ZIP_PATH)
    if use_zip:
        zf = zipfile.ZipFile(JSON_ZIP_PATH, 'r')
        filenames = sorted(
            [n for n in zf.namelist() if n.endswith('.json')],
            key=lambda x: int(os.path.splitext(x)[0])
        )
        print(f"Source: {JSON_ZIP_PATH}  ({len(filenames)} JSON files)")
    else:
        if not os.path.isdir(JSON_DIR_PATH):
            print(f"ERROR: neither {JSON_ZIP_PATH} nor {JSON_DIR_PATH} found.")
            return
        filenames = sorted(
            [f for f in os.listdir(JSON_DIR_PATH) if f.endswith('.json')],
            key=lambda x: int(os.path.splitext(x)[0])
        )
        print(f"Source: {JSON_DIR_PATH}  ({len(filenames)} JSON files)")

    total       = len(filenames)
    processed   = 0
    skipped     = 0

    db_conn = sqlite3.connect(DB_PATH)
    db_conn.execute("PRAGMA foreign_keys = ON;")
    db_conn.execute("PRAGMA journal_mode = WAL;")   # faster bulk inserts
    db_conn.execute("PRAGMA synchronous = NORMAL;")

    for i, filename in enumerate(filenames):
        base = os.path.basename(filename)
        print(f"\r  [{i+1:>4}/{total}] {base}  (ok={processed} skip={skipped})", end='', flush=True)

        try:
            if use_zip:
                content = zf.read(filename)
            else:
                with open(os.path.join(JSON_DIR_PATH, base), 'rb') as fh:
                    content = fh.read()

            with db_conn:                       # transaction per file
                process_file(db_conn, content, base)
            processed += 1

        except Exception as e:
            logging.error(f"FAILED {base}: {e}")
            skipped += 1

    if use_zip:
        zf.close()
    db_conn.close()

    elapsed = time.time() - start_time
    print(f"\n\n{'='*60}")
    print(f"Ingestion complete in {elapsed:.1f}s")
    print(f"  Processed : {processed}/{total}")
    print(f"  Skipped   : {skipped}")
    print(f"  Database  : {DB_PATH}")
    print(f"  Log       : {LOG_PATH}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
