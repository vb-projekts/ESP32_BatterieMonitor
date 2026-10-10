"""
Lese-/Schreibfunktionen für Garage-Tracking.

FAHRTENVERLAUF-LOGIK (v2.0):
========================================================================
Ein Fahrtenverlauf wird als "Trip" bezeichnet und folgt dieser Logik:

1. AUTO VERLÄSST GARAGE (Event: 'verlassen')
   → Neue Trip wird erstellt
   → Felder: ip, tor, auto_typ, verlassen_zeit
   → Felder LEER: angekommen_zeit (NULL), dauer_sekunden (NULL)

2. AUTO KOMMT ZURÜCK (Event: 'angekommen')
   → Suche die LETZTE offene Trip (angekommen_zeit IS NULL)
   → Prüfe: Wurde diese Trip mit einem 'verlassen' Event gestartet?
   → JA: Aktualisiere mit angekommen_zeit und dauer_sekunden
   → NEIN: Erstelle NEUE Trip (Sensor war möglicherweise defekt)

3. SENSOR DEFEKT / UNTERBROCHEN
   → Alte Trip bleibt OFFEN (angekommen_zeit = NULL, dauer = NULL)
   → Gerät startet neu oder Sensor repariert
   → Neue Trip wird erstellt
   → Alte Trip bleibt für Debugging sichtbar

WICHTIG: Die Logik ist ASYMMETRISCH
   - Verlassen-Events sind EINDEUTIG (Auto fährt raus)
   - Angekommen-Events sind MEHRDEUTIG (War das Sensor-Fehler?)
   - Daher: Nur 1:1 Verlassen↔Angekommen paaren
========================================================================
"""

from datetime import datetime
from . import get_connection


def insert_garage_event(ip, tor, event_type, zeitstempel=None, distanz_cm=None):
    """
    Speichert ein Garage-Event (Verlassen/Angekommen).
    
    Diese Events sind RAH-Daten für Debugging und Nachverfolgung.
    Sie werden auch verwendet, um zu prüfen, ob eine Trip gültig ist.
    
    Args:
        ip: IP-Adresse des Garage-Boards
        tor: Tor-Nummer (1 oder 2)
        event_type: 'verlassen' oder 'angekommen'
        zeitstempel: ISO-Timestamp (default: jetzt)
        distanz_cm: Sensor-Distanz zum Zeitpunkt des Events
    """
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
    """
    Öffnet eine neue Trip (Auto verlässt die Garage).
    
    WICHTIG: Diese Funktion wird IMMER aufgerufen, wenn ein 'verlassen'
    Event erkannt wird. Die Trip bleibt OFFEN, bis ein 'angekommen'
    Event sie schließt.
    
    Args:
        ip: IP-Adresse des Garage-Boards
        tor: Tor-Nummer (1 oder 2)
        auto_typ: 'ford' oder 'bmw'
        verlassen_zeit: ISO-Timestamp (default: jetzt)
    
    Returns:
        trip_id: Die ID der neu erstellten Trip (für Event-Tracking)
    """
    if verlassen_zeit is None:
        verlassen_zeit = datetime.now().isoformat(timespec="seconds")
    
    conn = get_connection()
    try:
        cursor = conn.execute(
            """INSERT INTO garage_trips (ip, tor, auto_typ, verlassen_zeit) 
               VALUES (?, ?, ?, ?)""",
            (ip, tor, auto_typ, verlassen_zeit)
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def close_trip(ip, tor, angekommen_zeit=None):
    """
    Schliesst die juengste noch offene Trip (angekommen_zeit IS NULL).
    
    Robustheitslogik bei System-/Sensorausfaellen:
    - Wurde das Verlassen waehrend eines Ausfalls verschluckt (keine offene Trip da),
      wird KEIN Eintrag geschlossen und KEIN Pseudo-Eintrag erzeugt.
      Grund: Fehlende Verlassens-Zeitpunkte lassen sich nicht sicher rekonstruieren;
      bisherige offene Trips bleiben genau so im DB-Zustand, wie sie waren.
      
    Returns:
        bool: True wenn eine offene Fahrt geschlossen wurde, False wenn keine vorhanden war.
    """
    if angekommen_zeit is None:
        angekommen_zeit = datetime.now().isoformat(timespec="seconds")
    
    conn = get_connection()
    try:
        # Suche die LETZTE offene Fahrt fuer dieses Tor
        row = conn.execute(
            """SELECT id, verlassen_zeit FROM garage_trips 
               WHERE ip = ? AND tor = ? AND angekommen_zeit IS NULL
               ORDER BY id DESC LIMIT 1""",
            (ip, tor)
        ).fetchone()
        
        if row:
            try:
                verlassen = datetime.fromisoformat(row['verlassen_zeit'])
                angekommen = datetime.fromisoformat(angekommen_zeit)
                dauer_sekunden = max(0, int((angekommen - verlassen).total_seconds()))
            except Exception:
                dauer_sekunden = None
            
            conn.execute(
                """UPDATE garage_trips 
                   SET angekommen_zeit = ?, dauer_sekunden = ?
                   WHERE id = ?""",
                (angekommen_zeit, dauer_sekunden, row['id'])
            )
            conn.commit()
            return True
        else:
            # Keine offene Trip vorhanden (z.B. Verlassen verschluckt)
            # -> Nichts ueberschreiben, keine falschen Daten erzeugen.
            return False
    finally:
        conn.close()


def get_recent_trips(ip, tor, limit=10):
    """
    Gibt die letzten Trips für einen Tor.
    
    Zeigt ALLE Trips an, auch die noch offenen (angekommen_zeit = NULL).
    
    Args:
        ip: IP-Adresse des Garage-Boards
        tor: Tor-Nummer (1 oder 2)
        limit: Anzahl der anzuzeigenden Trips (default: 10)
    
    Returns:
        Liste von Trip-Dicts mit allen Feldern
    """
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
    """
    Formatiert Sekunden zu HH:MM:SS.
    
    Args:
        seconds: Anzahl der Sekunden (oder None)
    
    Returns:
        Formatierter String oder "--:--:--" wenn None
    """
    if seconds is None:
        return "--:--:--"
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h:02d}:{m:02d}:{s:02d}"


def get_open_trips(ip, tor):
    """
    Gibt die OFFENEN Trips (noch nicht angekommen) zurück.
    
    Nützlich für UI-Anzeige: "Auto ist unterwegs seit..."
    
    Args:
        ip: IP-Adresse des Garage-Boards
        tor: Tor-Nummer (1 oder 2)
    
    Returns:
        Liste von offenen Trip-Dicts
    """
    conn = get_connection()
    try:
        rows = conn.execute(
            """SELECT id, auto_typ, verlassen_zeit, angekommen_zeit, dauer_sekunden 
               FROM garage_trips 
               WHERE ip = ? AND tor = ? AND angekommen_zeit IS NULL
               ORDER BY verlassen_zeit DESC""",
            (ip, tor)
        ).fetchall()
        
        return [dict(row) for row in rows]
    finally:
        conn.close()
