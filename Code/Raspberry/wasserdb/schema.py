"""SQL-Schema fuer die Wasserverbrauch-Datenbank."""

SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS messwerte (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        ip            TEXT NOT NULL,
        zeitstempel   TEXT NOT NULL,
        liter_gesamt  REAL NOT NULL
    )
    """,
    "CREATE INDEX IF NOT EXISTS idx_messwerte_ip_zeit ON messwerte(ip, zeitstempel)",
    """
    CREATE TABLE IF NOT EXISTS verbrauch_stunde (
        ip TEXT NOT NULL, stunde TEXT NOT NULL, liter_verbrauch REAL NOT NULL,
        PRIMARY KEY (ip, stunde)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS verbrauch_tag (
        ip TEXT NOT NULL, tag TEXT NOT NULL, liter_verbrauch REAL NOT NULL,
        PRIMARY KEY (ip, tag)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS verbrauch_woche (
        ip TEXT NOT NULL, jahr INTEGER NOT NULL, kw INTEGER NOT NULL,
        liter_verbrauch REAL NOT NULL, PRIMARY KEY (ip, jahr, kw)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS verbrauch_monat (
        ip TEXT NOT NULL, monat TEXT NOT NULL, liter_verbrauch REAL NOT NULL,
        PRIMARY KEY (ip, monat)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lebenszeit_verbrauch (
        ip TEXT PRIMARY KEY,
        gesamt_liter REAL NOT NULL,
        letzter_bekannter_wert REAL,
        letzter_zeitstempel TEXT
    )
    """,
]
