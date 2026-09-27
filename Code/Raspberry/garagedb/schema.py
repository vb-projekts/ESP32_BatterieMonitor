"""SQL-Schema für die Garage-Tracking-Datenbank."""

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS garage_events (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        ip              TEXT NOT NULL,
        tor             INTEGER NOT NULL,  -- 1 oder 2
        event_type      TEXT NOT NULL,     -- 'verlassen' oder 'angekommen'
        zeitstempel     TEXT NOT NULL,
        distanz_cm      REAL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_garage_events_ip_tor ON garage_events(ip, tor, zeitstempel)",
    
    """
    CREATE TABLE IF NOT EXISTS garage_trips (
        id              INTEGER PRIMARY KEY AUTOINCREMENT,
        ip              TEXT NOT NULL,
        tor             INTEGER NOT NULL,  -- 1 oder 2
        auto_typ        TEXT NOT NULL,     -- 'ford' oder 'bmw'
        verlassen_zeit  TEXT NOT NULL,     -- ISO timestamp
        angekommen_zeit TEXT,               -- ISO timestamp (NULL wenn noch weg)
        dauer_sekunden  INTEGER,            -- Berechnet: angekommen_zeit - verlassen_zeit
        FOREIGN KEY (ip, tor) REFERENCES garage_events(ip, tor)
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_garage_trips_ip_tor ON garage_trips(ip, tor, verlassen_zeit DESC)",
]
