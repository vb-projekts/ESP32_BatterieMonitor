"""Lese-/Schreibfunktionen für Garage-Tracking."""

from datetime import datetime
from . import get_connection


def insert_garage_event(ip, tor, event_type, zeitstempel=None, distanz_cm=None):
    """Speichert ein Garage-Event (Verlassen/Angekommen)."""
    if zeitstempel is None:
        zeitstempel = datetime.now().isoformat(timespec="seconds")
    
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO garage_events (ip, tor, event_type, zeitstempel, distanz_cm) 
               VALUES (?, ?, ?, ?, ?)""",
            (ip, tor, event_type, zeitstempel, distanz_cm)
        )
        conn.commit()
    finally:
        conn.close()


def open_trip(ip, tor, auto_typ, verlassen_zeit=None):
    """Öffnet eine neue Trip (Auto verlässt die Garage)."""
    if verlassen_zeit is None:
        verlassen_zeit = datetime.now().isoformat(timespec="seconds")
    
    conn = get_connection()
    try:
        conn.execute(
            """INSERT INTO garage_trips (ip, tor, auto_typ, verlassen_zeit) 
               VALUES (?, ?, ?, ?)""",
            (ip, tor, auto_typ, verlassen_zeit)
        )
        conn.commit()
    finally:
        conn.close()


def close_trip(ip, tor, angekommen_zeit=None):
    """Schließt eine offene Trip (Auto ist zurückgekommen)."""
    if angekommen_zeit is None:
        angekommen_zeit = datetime.now().isoformat(timespec="seconds")
    
    conn = get_connection()
    try:
        # Finde die letzte offene Trip
        row = conn.execute(
            """SELECT id, verlassen_zeit FROM garage_trips 
               WHERE ip = ? AND tor = ? AND angekommen_zeit IS NULL
               ORDER BY verlassen_zeit DESC LIMIT 1""",
            (ip, tor)
        ).fetchone()
        
        if row:
            verlassen = datetime.fromisoformat(row['verlassen_zeit'])
            angekommen = datetime.fromisoformat(angekommen_zeit)
            dauer_sekunden = int((angekommen - verlassen).total_seconds())
            
            conn.execute(
                """UPDATE garage_trips 
                   SET angekommen_zeit = ?, dauer_sekunden = ?
                   WHERE id = ?""",
                (angekommen_zeit, dauer_sekunden, row['id'])
            )
            conn.commit()
    finally:
        conn.close()


def get_recent_trips(ip, tor, limit=10):
    """Gibt die letzten Trips für einen Tor."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, auto_typ, verlassen_zeit, angekommen_zeit, dauer_sekunden 
               FROM garage_trips 
               WHERE ip = ? AND tor = ?
               ORDER BY verlassen_zeit DESC 
               LIMIT ?""",
            (ip, tor, limit)
        ).fetchall()
        
        return [dict(row) for row in rows]
    finally:
        conn.close()


def format_duration(seconds):
    """Formatiert Sekunden zu HH:MM:SS."""
    if seconds is None:
        return "--:--:--"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"
