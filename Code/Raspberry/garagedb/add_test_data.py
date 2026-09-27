#!/usr/bin/env python3
"""
Test-Daten Generator für Garage-Tracking
Initialisiert zuerst die Datenbank, dann fügt Beispiel-Fahrten ein
"""

import sys
import os
from datetime import datetime, timedelta

# Füge den aktuellen Verzeichnis zum Path hinzu
current_dir = os.path.dirname(os.path.abspath(__file__))
parent_dir = os.path.dirname(current_dir)
if parent_dir not in sys.path:
    sys.path.insert(0, parent_dir)

print(f"Working Directory: {os.getcwd()}")
print(f"Script Directory: {current_dir}")
print(f"Parent Directory: {parent_dir}")
print()

try:
    from garagedb import get_connection, init_db
    print("✅ garagedb erfolgreich importiert")
except ImportError as e:
    print(f"❌ Fehler beim Import: {e}")
    print()
    print("Lösung: Führe das Script aus dem Webserver-Verzeichnis aus:")
    print("  cd /path/to/esp32-monitor")
    print("  python3 garagedb/add_test_data.py")
    sys.exit(1)

def add_test_trips():
    """Fügt Test-Fahrten für beide Autos ein"""
    
    # Zuerst: Datenbank initialisieren
    print("📊 Initialisiere Datenbank...")
    try:
        init_db()
        print("✅ Datenbank initialisiert")
    except Exception as e:
        print(f"⚠️  Fehler bei DB-Init (ignoriert): {e}")
    
    print()
    
    conn = get_connection()
    
    try:
        # Test-Daten
        ip = "192.168.178.144"
        
        # Tor 1 - Ford Focus (Blau)
        trips_tor1 = [
            {
                'tor': 1,
                'auto_typ': 'ford',
                'verlassen_zeit': (datetime.now() - timedelta(hours=4)).isoformat(timespec="seconds"),
                'angekommen_zeit': (datetime.now() - timedelta(hours=2, minutes=15)).isoformat(timespec="seconds"),
                'dauer_sekunden': int(1.75 * 3600)  # 1h 45min
            },
            {
                'tor': 1,
                'auto_typ': 'ford',
                'verlassen_zeit': (datetime.now() - timedelta(hours=1, minutes=30)).isoformat(timespec="seconds"),
                'angekommen_zeit': (datetime.now() - timedelta(minutes=15)).isoformat(timespec="seconds"),
                'dauer_sekunden': int(1.25 * 3600)  # 1h 15min
            },
        ]
        
        # Tor 2 - BMW (Schwarz)
        trips_tor2 = [
            {
                'tor': 2,
                'auto_typ': 'bmw',
                'verlassen_zeit': (datetime.now() - timedelta(hours=5)).isoformat(timespec="seconds"),
                'angekommen_zeit': (datetime.now() - timedelta(hours=3, minutes=45)).isoformat(timespec="seconds"),
                'dauer_sekunden': int(1.25 * 3600)  # 1h 15min
            },
            {
                'tor': 2,
                'auto_typ': 'bmw',
                'verlassen_zeit': (datetime.now() - timedelta(hours=2)).isoformat(timespec="seconds"),
                'angekommen_zeit': (datetime.now() - timedelta(minutes=30)).isoformat(timespec="seconds"),
                'dauer_sekunden': int(1.5 * 3600)  # 1h 30min
            },
        ]
        
        all_trips = trips_tor1 + trips_tor2
        
        # Einfügen
        print("📝 Füge Test-Fahrten ein...")
        for trip in all_trips:
            conn.execute(
                """INSERT INTO garage_trips (ip, tor, auto_typ, verlassen_zeit, angekommen_zeit, dauer_sekunden) 
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (ip, trip['tor'], trip['auto_typ'], trip['verlassen_zeit'], trip['angekommen_zeit'], trip['dauer_sekunden'])
            )
        
        conn.commit()
        
        print("✅ Test-Daten erfolgreich eingefügt!")
        print()
        print(f"Tor 1 (Ford Focus): {len(trips_tor1)} Fahrten")
        print(f"Tor 2 (BMW): {len(trips_tor2)} Fahrten")
        print()
        print("Fahrten:")
        for trip in all_trips:
            tor = trip['tor']
            auto = '🔵 Ford Focus' if trip['auto_typ'] == 'ford' else '⚫ BMW'
            verlassen = datetime.fromisoformat(trip['verlassen_zeit']).strftime("%H:%M:%S")
            angekommen = datetime.fromisoformat(trip['angekommen_zeit']).strftime("%H:%M:%S")
            dauer = f"{trip['dauer_sekunden']//3600:02d}:{(trip['dauer_sekunden']%3600)//60:02d}:{trip['dauer_sekunden']%60:02d}"
            print(f"  Tor {tor}: {verlassen} → {angekommen} (Dauer: {dauer})")
        
    except Exception as e:
        print(f"❌ Fehler beim Einfügen: {e}")
        import traceback
        traceback.print_exc()
    finally:
        conn.close()

if __name__ == "__main__":
    print("🚗 Garage-Tracking Test-Daten Generator")
    print("=" * 60)
    print()
    add_test_trips()
    print()
    print("=" * 60)
    print("✅ Fertig!")
    print()
    print("Nächste Schritte:")
    print("  1. Server neu starten: sudo systemctl restart esp32-monitor")
    print("  2. Öffne die Garage-Seite im Browser")
    print("  3. Klicke auf das 👁️ Symbol")
    print("  4. Du solltest jetzt die Test-Fahrten sehen!")
