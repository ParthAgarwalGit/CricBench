-- CricBench IPL schema (franchise-based T20).
-- Teams are franchises (not nations); `season` denotes the IPL edition and
-- `stage` distinguishes group vs. knockout matches. Compare with
-- schemas/international.sql, used for Test / ODI / T20I.

PRAGMA foreign_keys = OFF;

CREATE TABLE Players (
    player_id   TEXT PRIMARY KEY,
    player_name TEXT NOT NULL
);

CREATE TABLE Matches (
    match_id            INTEGER PRIMARY KEY,
    season              TEXT    NOT NULL,   -- IPL edition, e.g. '2023'
    match_date          TEXT    NOT NULL,
    venue               TEXT    NOT NULL,
    city                TEXT,
    stage               TEXT    DEFAULT 'Group',  -- 'Group' | 'Qualifier' | 'Final' | ...
    team1               TEXT    NOT NULL,
    team2               TEXT    NOT NULL,
    toss_winner         TEXT    NOT NULL,
    toss_decision       TEXT    NOT NULL,
    match_winner        TEXT,               -- NULL for no result
    result_type         TEXT,               -- 'runs' | 'wickets' | 'tie' | 'no result'
    result_margin       INTEGER,
    player_of_match_id  TEXT,
    umpire1             TEXT,
    umpire2             TEXT,
    FOREIGN KEY (player_of_match_id) REFERENCES Players (player_id)
);

CREATE TABLE Deliveries (
    delivery_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id        INTEGER NOT NULL,
    inning          INTEGER NOT NULL,
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
    FOREIGN KEY (match_id)       REFERENCES Matches (match_id),
    FOREIGN KEY (striker_id)     REFERENCES Players (player_id),
    FOREIGN KEY (non_striker_id) REFERENCES Players (player_id),
    FOREIGN KEY (bowler_id)      REFERENCES Players (player_id),
    FOREIGN KEY (player_out_id)  REFERENCES Players (player_id)
);

CREATE TABLE PlayerInMatch (
    match_id  INTEGER NOT NULL,
    player_id TEXT    NOT NULL,
    team_name TEXT    NOT NULL,
    PRIMARY KEY (match_id, player_id),
    FOREIGN KEY (match_id)  REFERENCES Matches (match_id),
    FOREIGN KEY (player_id) REFERENCES Players (player_id)
);

CREATE TABLE FielderDismissals (
    fielder_dismissal_id INTEGER PRIMARY KEY AUTOINCREMENT,
    delivery_id          INTEGER NOT NULL,
    fielder_id           TEXT    NOT NULL,
    FOREIGN KEY (delivery_id) REFERENCES Deliveries (delivery_id),
    FOREIGN KEY (fielder_id)  REFERENCES Players    (player_id)
);

PRAGMA foreign_keys = ON;
