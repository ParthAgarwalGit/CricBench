PRAGMA foreign_keys=OFF;

-- Players: universal, unchanged
CREATE TABLE IF NOT EXISTS Players (
    player_id   TEXT PRIMARY KEY,
    player_name TEXT NOT NULL
);

-- Matches: adapted for Test cricket
--   * start_date / end_date replace single match_date
--   * series_name replaces stage (Tests belong to a named series)
--   * match_type_number tracks match number within a series
--   * gender and team_type added (international / male|female)
--   * result_type extended to cover 'runs', 'wickets', 'draw', 'tie', 'no result'
CREATE TABLE IF NOT EXISTS Matches (
    match_id            INTEGER PRIMARY KEY,
    season              TEXT    NOT NULL,
    start_date          TEXT    NOT NULL,   -- first day of match
    end_date            TEXT,               -- last day played
    venue               TEXT    NOT NULL,
    city                TEXT,
    series_name         TEXT,               -- e.g. "Border-Gavaskar Trophy"
    match_type_number   INTEGER,            -- match number within the series
    gender              TEXT,               -- 'male' | 'female'
    team_type           TEXT,               -- 'international' | 'club'
    team1               TEXT    NOT NULL,
    team2               TEXT    NOT NULL,
    toss_winner         TEXT    NOT NULL,
    toss_decision       TEXT    NOT NULL,
    match_winner        TEXT,               -- NULL for draws / no results
    result_type         TEXT,               -- 'runs' | 'wickets' | 'draw' | 'tie' | 'no result'
    result_margin       INTEGER,            -- NULL for draws / ties / no results
    player_of_match_id  TEXT,
    umpire1             TEXT,
    umpire2             TEXT,
    tv_umpire           TEXT,
    match_referee       TEXT,
    FOREIGN KEY (player_of_match_id) REFERENCES Players (player_id)
);

-- Deliveries: unchanged structurally; inning 1-4 covers all Test innings
CREATE TABLE IF NOT EXISTS Deliveries (
    delivery_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL,
    inning          INTEGER NOT NULL,   -- 1, 2, 3, or 4
    over_number     INTEGER NOT NULL,
    ball_number     INTEGER NOT NULL,   -- legal ball number (1-6)
    batting_team    TEXT    NOT NULL,
    bowling_team    TEXT    NOT NULL,
    striker_id      TEXT    NOT NULL,
    non_striker_id  TEXT    NOT NULL,
    bowler_id       TEXT    NOT NULL,
    runs_scored     INTEGER NOT NULL,   -- runs off bat
    extra_runs      INTEGER NOT NULL,   -- total extras this ball
    wides           INTEGER DEFAULT 0,
    noballs         INTEGER DEFAULT 0,
    byes            INTEGER DEFAULT 0,
    legbyes         INTEGER DEFAULT 0,
    wicket_type     TEXT,
    player_out_id   TEXT,
    FOREIGN KEY (match_id)        REFERENCES Matches   (match_id),
    FOREIGN KEY (striker_id)      REFERENCES Players   (player_id),
    FOREIGN KEY (non_striker_id)  REFERENCES Players   (player_id),
    FOREIGN KEY (bowler_id)       REFERENCES Players   (player_id),
    FOREIGN KEY (player_out_id)   REFERENCES Players   (player_id)
);

-- Playing XI per match
CREATE TABLE IF NOT EXISTS PlayerInMatch (
    match_id    INTEGER NOT NULL,
    player_id   TEXT    NOT NULL,
    team_name   TEXT    NOT NULL,
    PRIMARY KEY (match_id, player_id),
    FOREIGN KEY (match_id)  REFERENCES Matches (match_id),
    FOREIGN KEY (player_id) REFERENCES Players (player_id)
);

-- Fielder dismissals (caught, run-out, stumped, etc.)
CREATE TABLE IF NOT EXISTS FielderDismissals (
    fielder_dismissal_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id           INTEGER NOT NULL,
    fielder_id            TEXT    NOT NULL,
    FOREIGN KEY (delivery_id) REFERENCES Deliveries (delivery_id),
    FOREIGN KEY (fielder_id)  REFERENCES Players    (player_id)
);

PRAGMA foreign_keys=ON;
