#!/usr/bin/env python3
# ============================================================
#  Raspberry Pi Flask Server - Kombiniert
#  Empfaengt Daten von:
#    - ESP32 Ultraschall-Monitor (Uptime_Schall.ino)  -> sensor_typ fehlt ODER "HC-SR04"
#    - ESP32 Wasser-Monitor      (Uptime_LJ18A3.ino)  -> sensor_typ = "LJ18A3"
#
#  v2.2 - Frontend auf fetch()-Polling umgestellt (kein <meta refresh> mehr!)
#         HTML/CSS/JS liegen jetzt in templates/ und static/ (siehe unten).
#  v2.4 - Neue Seite /wasser (Wasserverbrauch + rotierende Wasseruhr),
#         Durchfluss-Berechnung (L/min), eigener Endpunkt /api/wasser.
#  v2.5 - SQLite-Datenhaltung (wasserdb-Paket): Rohdaten 14 Tage, Rollup
#         zu Stunde/Tag/Woche(Mo-So)/Monat, Endpunkt /api/wasser/verlauf.
#  v2.6 - Kalibrierbarer Lebenszeit-Gesamtverbrauch, passwortgeschuetzte
#         Admin-Seite (/admin), redundantes Session-Feld entfernt.
#
#  v2.7 - Durchfluss-Anzeige exponentiell geglaettet (kein Springen mehr
#         zwischen 0 und Spitzenwert), Wasserrad dreht dadurch weich.
#
#  Struktur:
#    server.py
#    templates/index.html   -> HTML-Grundgeruest
#    static/css/style.css   -> alle Styles
#    static/js/app.js       -> fetch()-Polling, aktualisiert DOM alle 3s
#
#  Neuer Endpunkt:
#    GET /api/status  -> JSON mit allen Board-Daten (fuer das Frontend-JS)
#
#  OTA Firmware Update Endpunkte (GETRENNT pro Typ!):
#    Schall:  GET /firmware/schall/version   -> aktuelle Version
#             GET /firmware/schall/download  -> .bin Datei
#    LJ18A3:  GET /firmware/lj18a3/version   -> aktuelle Version
#             GET /firmware/lj18a3/download  -> .bin Datei
#
#  Start:  python server.py
#  Port:   5000
#
#  Nach Aenderungen neu starten:
#    sudo systemctl restart esp32-monitor
# ============================================================

from flask import Flask, request, jsonify, render_template, send_file, session, redirect, url_for
from datetime import datetime
import threading
import os
import secrets

from wasserdb import init_db
from wasserdb.rollup import starte_rollup_thread
from wasserdb.queries import (
    insert_messwert,
    liste_geraete_ips,
    hole_verlauf,
    hole_lebenszeit_verbrauch,
    kalibriere_lebenszeit,
)

# Flask findet templates/ und static/ automatisch, weil sie direkt
# neben server.py liegen (Standard-Konvention, explizit hier notiert
# damit es beim Erweitern - z.B. weitere Seiten - klar bleibt).
app = Flask(__name__, template_folder="templates", static_folder="static")
# Fuer die Admin-Login-Session (Flask signiert das Session-Cookie damit).
# Wird bei jedem Neustart neu erzeugt -> vorhandene Logins muessen sich nach
# einem Neustart des Servers erneut anmelden. Fuer ein Heimnetz ausreichend.
app.secret_key = secrets.token_hex(32)
data_lock = threading.Lock()

# ACHTUNG: Vor dem produktiven Einsatz aendern! Schuetzt die Admin-Seite
# (/admin), auf der sich der Gesamtverbrauch-Zaehler kalibrieren laesst.
ADMIN_PASSWORT = "aendere-mich"

# SQLite-Datenhaltung fuer den Wasserverbrauch: Tabellen anlegen (falls noch
# nicht vorhanden) und den Rollup-Hintergrundjob starten (Stunde/Tag/Woche/
# Monat aggregieren, Rohdaten aelter als 14 Tage aufraeumen).
init_db()
starte_rollup_thread()


def ist_admin_eingeloggt():
    return session.get("ist_admin", False) is True


@app.context_processor
def inject_server_version():
    """Macht server_version in ALLEN Templates verfuegbar (auch kuenftigen Seiten),
    ohne dass jeder render_template()-Aufruf sie einzeln mitgeben muss."""
    return dict(server_version=SERVER_VERSION)

# Nach wie vielen Sekunden ohne neues Signal gilt ein Board als OFFLINE?
OFFLINE_SECS = 30

# Glaettungsfaktor fuer die Durchfluss-Anzeige (0 < x <= 1).
# Kleiner = traeger/glatter, groesser = reagiert schneller aber unruhiger.
DURCHFLUSS_GLAETTUNG = 0.3

# Server-Version, wird in der Web-UI angezeigt (Nav-Leiste), damit man
# beim Aktualisieren der Dateien auf dem Pi den Ueberblick behaelt.
SERVER_VERSION = "2.7"

# ============================================================
#  Firmware Pfade
# ============================================================
BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
FW_SCHALL_DIR    = os.path.join(BASE_DIR, "firmware", "schall")
FW_LJ18A3_DIR    = os.path.join(BASE_DIR, "firmware", "lj18a3")
FW_SCHALL_BIN    = os.path.join(FW_SCHALL_DIR, "firmware.bin")
FW_LJ18A3_BIN    = os.path.join(FW_LJ18A3_DIR, "firmware.bin")
FW_SCHALL_VER    = os.path.join(FW_SCHALL_DIR, "version.txt")
FW_LJ18A3_VER    = os.path.join(FW_LJ18A3_DIR, "version.txt")

os.makedirs(FW_SCHALL_DIR, exist_ok=True)
os.makedirs(FW_LJ18A3_DIR, exist_ok=True)


def lese_version(pfad):
    """Liest Versionsnummer aus Textdatei, gibt '0.0' zurueck falls nicht vorhanden."""
    try:
        with open(pfad, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "0.0"


def ist_online(device):
    """True, wenn das Board innerhalb von OFFLINE_SECS zuletzt gemeldet hat."""
    letzter_kontakt = device.get("_last_seen_dt")
    if letzter_kontakt is None:
        return False
    delta = (datetime.now() - letzter_kontakt).total_seconds()
    return delta <= OFFLINE_SECS


# ============================================================
#  Geraete-Datenspeicher - getrennt nach Sensor-Typ
#  Schluessel = IP-Adresse des ESP32
# ============================================================
devices_schall = {}   # HC-SR04 Ultraschall Geraete
devices_lj18a3 = {}   # LJ18A3 Wasser-Monitor Geraete

# Nachrichten-Log (letzte 100 Eintraege)
messages = []


# ============================================================
#  API Endpunkt - Sensordaten empfangen (von den ESP32-Boards)
# ============================================================
@app.route("/api/data", methods=["POST"])
def empfange_daten():
    global messages

    try:
        daten = request.get_json(force=True)
        if not daten:
            return jsonify({"fehler": "Kein JSON empfangen"}), 400

        ip         = daten.get("ip", request.remote_addr)
        now_str    = datetime.now().strftime("%H:%M:%S")
        sensor_typ = daten.get("sensor_typ", "HC-SR04")

        jetzt = datetime.now()

        with data_lock:
            if sensor_typ == "LJ18A3":
                # Durchfluss (L/min) aus der Differenz zum letzten Messwert berechnen.
                # Notwendig, weil das Board nur den Zaehlerstand (liter_gesamt) sendet,
                # keine Momentan-Fliessgeschwindigkeit.
                vorheriges = devices_lj18a3.get(ip)
                neuer_liter_gesamt = float(daten.get("liter_gesamt", 0))
                momentaner_durchfluss = 0.0
                if vorheriges is not None:
                    delta_liter = neuer_liter_gesamt - vorheriges.get("liter_gesamt", 0.0)
                    delta_sek   = (jetzt - vorheriges.get("_last_seen_dt", jetzt)).total_seconds()
                    # negative Delta (z.B. Zaehler-Reset nach Neustart) ignorieren
                    if delta_sek > 0 and delta_liter >= 0:
                        momentaner_durchfluss = (delta_liter / delta_sek) * 60.0

                # Exponentielle Glaettung: Der Momentanwert (aus nur EINEM Impuls
                # in einem 2s-Fenster) springt sonst hart zwischen 0 und z.B. 30 L/min.
                # Statt den Momentanwert direkt zu uebernehmen, wird er nur zu
                # DURCHFLUSS_GLAETTUNG-Anteil eingerechnet - der Rest kommt vom
                # zuletzt angezeigten (schon geglaetteten) Wert. Ergebnis: sanftes
                # Hoch-/Runterlaufen statt Sprung, das Wasserrad dreht dadurch
                # automatisch weich schneller/langsamer statt abrupt zu stoppen.
                vorheriger_geglaetteter_wert = vorheriges.get("durchfluss_l_min", 0.0) if vorheriges else 0.0
                durchfluss_l_min = round(
                    DURCHFLUSS_GLAETTUNG * momentaner_durchfluss
                    + (1 - DURCHFLUSS_GLAETTUNG) * vorheriger_geglaetteter_wert,
                    3,
                )

                devices_lj18a3[ip] = {
                    "uptime":           daten.get("uptime", "--"),
                    "uptime_ms":        daten.get("uptime_ms", 0),
                    "liter_gesamt":     neuer_liter_gesamt,
                    "impulse_gesamt":   int(daten.get("impulse_gesamt", 0)),
                    "batterie_v":       float(daten.get("batterie_v", 0)),
                    "firmware":         daten.get("firmware", "?"),
                    "display_an":       bool(daten.get("display_an", True)),
                    "durchfluss_l_min": durchfluss_l_min,
                    "last_seen":        now_str,
                    "_last_seen_dt":    jetzt,
                }
                # Rohdaten-Messwert fuer die spaetere stunden-/tage-/wochen-/
                # monatsweise Auswertung in SQLite speichern (wasserdb-Paket).
                # Aktualisiert dabei automatisch auch den kalibrierbaren
                # Lebenszeit-Zaehler (siehe wasserdb.queries).
                insert_messwert(ip, neuer_liter_gesamt)
                details = (f"Liter: {neuer_liter_gesamt:.1f} L | "
                           f"Durchfluss: {durchfluss_l_min:.2f} L/min | "
                           f"Batt: {daten.get('batterie_v', 0):.2f}V | "
                           f"FW: v{daten.get('firmware', '?')}")
            else:
                devices_schall[ip] = {
                    "uptime":     daten.get("uptime", "--"),
                    "uptime_ms":  daten.get("uptime_ms", 0),
                    "distanz_cm": float(daten.get("distanz_cm", -1)),
                    "batterie_v": float(daten.get("batterie_v", 0)),
                    "firmware":   daten.get("firmware", "?"),
                    "display_an": bool(daten.get("display_an", True)),
                    "last_seen":  now_str,
                    "_last_seen_dt": datetime.now(),
                }
                details = (f"Distanz: {daten.get('distanz_cm', -1)} cm | "
                           f"Batt: {daten.get('batterie_v', 0):.2f}V | "
                           f"FW: v{daten.get('firmware', '?')}")

            if sensor_typ == "LJ18A3":
                messages.append({
                    "zeit":           now_str,
                    "ip":             ip,
                    "typ":            sensor_typ,
                    "details":        details,
                    "impulse_gesamt": int(daten.get("impulse_gesamt", 0)),
                    "liter_gesamt":   float(daten.get("liter_gesamt", 0)),
                    "distanz_cm":     -1,
                    "batterie_v":     float(daten.get("batterie_v", 0)),
                })
            else:
                messages.append({
                    "zeit":           now_str,
                    "ip":             ip,
                    "typ":            sensor_typ,
                    "details":        details,
                    "impulse_gesamt": 0,
                    "liter_gesamt":   0.0,
                    "distanz_cm":     float(daten.get("distanz_cm", -1)),
                    "batterie_v":     float(daten.get("batterie_v", 0)),
                })
            if len(messages) > 100:
                messages = messages[-100:]

        print(f"[{now_str}] {sensor_typ} von {ip}: {details}")
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print(f"Fehler beim Verarbeiten: {e}")
        return jsonify({"fehler": str(e)}), 500


# ============================================================
#  Hilfsfunktionen: Geraete-Dicts in JSON-taugliche Listen umwandeln
#  (gemeinsam genutzt von /api/status UND /api/wasser)
# ============================================================
def _lj18a3_liste():
    liste = []
    for ip, d in devices_lj18a3.items():
        d2 = {k: v for k, v in d.items() if k != "_last_seen_dt"}
        d2["ip"] = ip
        d2["online"] = ist_online(d)
        d2["liter_lebenszeit"] = hole_lebenszeit_verbrauch(ip)
        liste.append(d2)
    return liste


def _schall_liste():
    liste = []
    for ip, d in devices_schall.items():
        d2 = {k: v for k, v in d.items() if k != "_last_seen_dt"}
        d2["ip"] = ip
        d2["online"] = ist_online(d)
        liste.append(d2)
    return liste


# ============================================================
#  API Endpunkt - aktueller Status fuer das Frontend (JS-Polling)
# ============================================================
@app.route("/api/status")
def api_status():
    with data_lock:
        devices_lj18a3_liste = _lj18a3_liste()
        devices_schall_liste = _schall_liste()

        alle = devices_lj18a3_liste + devices_schall_liste
        anzahl_gesamt  = len(alle)
        anzahl_online  = sum(1 for d in alle if d["online"])
        anzahl_offline = anzahl_gesamt - anzahl_online

        letzte_nachrichten = list(reversed(messages[-20:]))

        return jsonify({
            "now":          datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "offline_secs": OFFLINE_SECS,
            "summary": {
                "gesamt":  anzahl_gesamt,
                "online":  anzahl_online,
                "offline": anzahl_offline,
            },
            "devices_lj18a3": devices_lj18a3_liste,
            "devices_schall": devices_schall_liste,
            "firmware": {
                "lj18a3": {"version": lese_version(FW_LJ18A3_VER), "ok": os.path.exists(FW_LJ18A3_BIN)},
                "schall": {"version": lese_version(FW_SCHALL_VER), "ok": os.path.exists(FW_SCHALL_BIN)},
            },
            "messages": letzte_nachrichten,
            "server_version": SERVER_VERSION,
        })


# ============================================================
#  API Endpunkt - Wasserverbrauch-Seite (eigener, schlanker Endpunkt)
# ============================================================
@app.route("/api/wasser")
def api_wasser():
    with data_lock:
        geraete = _lj18a3_liste()
        lebenszeit_gesamt   = sum(d["liter_lebenszeit"] for d in geraete)
        seit_neustart_gesamt = sum(d["liter_gesamt"] for d in geraete)
        durchfluss_sum = sum(d.get("durchfluss_l_min", 0.0) for d in geraete)

        return jsonify({
            "now":          datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "offline_secs": OFFLINE_SECS,
            "geraete": geraete,
            "summary": {
                "liter_lebenszeit":    round(lebenszeit_gesamt, 1),
                "liter_seit_neustart": round(seit_neustart_gesamt, 1),
                "durchfluss_l_min":    round(durchfluss_sum, 3),
            },
            "server_version": SERVER_VERSION,
        })


# ============================================================
#  API Endpunkt - Verbrauchsverlauf (Stunde/Tag/Woche/Monat) fuers Diagramm
# ============================================================
@app.route("/api/wasser/verlauf")
def api_wasser_verlauf():
    ip = request.args.get("ip")
    zeitraum = request.args.get("zeitraum", "tag")
    try:
        anzahl = int(request.args.get("anzahl", 30))
    except ValueError:
        anzahl = 30

    if not ip:
        # Keine IP angegeben -> erstes bekanntes Geraet verwenden
        geraete = liste_geraete_ips()
        if not geraete:
            return jsonify({"ip": None, "zeitraum": zeitraum, "labels": [], "werte": []})
        ip = geraete[0]

    try:
        daten = hole_verlauf(ip, zeitraum, anzahl=anzahl)
    except ValueError as e:
        return jsonify({"fehler": str(e)}), 400

    return jsonify({
        "ip": ip,
        "zeitraum": zeitraum,
        "labels": [d["label"] for d in daten],
        "werte":  [d["liter"] for d in daten],
    })


# ============================================================
#  OTA Endpunkte - SCHALL (HC-SR04)
# ============================================================
@app.route("/firmware/schall/version", methods=["GET"])
def fw_schall_version():
    ver = lese_version(FW_SCHALL_VER)
    return jsonify({"version": ver, "typ": "HC-SR04"}), 200


@app.route("/firmware/schall/download", methods=["GET"])
def fw_schall_download():
    if not os.path.exists(FW_SCHALL_BIN):
        return "Keine Schall-Firmware vorhanden", 404
    return send_file(FW_SCHALL_BIN,
                     mimetype="application/octet-stream",
                     as_attachment=True,
                     download_name="firmware_schall.bin")


# ============================================================
#  OTA Endpunkte - LJ18A3 (Wasser-Monitor)
# ============================================================
@app.route("/firmware/lj18a3/version", methods=["GET"])
def fw_lj18a3_version():
    ver = lese_version(FW_LJ18A3_VER)
    return jsonify({"version": ver, "typ": "LJ18A3"}), 200


@app.route("/firmware/lj18a3/download", methods=["GET"])
def fw_lj18a3_download():
    if not os.path.exists(FW_LJ18A3_BIN):
        return "Keine LJ18A3-Firmware vorhanden", 404
    return send_file(FW_LJ18A3_BIN,
                     mimetype="application/octet-stream",
                     as_attachment=True,
                     download_name="firmware_lj18a3.bin")


# ============================================================
#  Admin-Seite - Kalibrierung des Lebenszeit-Gesamtverbrauchs.
#  Passwortgeschuetzt ueber eine simple Session (siehe ADMIN_PASSWORT).
# ============================================================
@app.route("/admin", methods=["GET"])
def admin_seite():
    if not ist_admin_eingeloggt():
        return render_template("admin_login.html")
    with data_lock:
        geraete = _lj18a3_liste()
    return render_template("admin.html", geraete=geraete)


@app.route("/admin/login", methods=["POST"])
def admin_login():
    passwort = request.form.get("passwort", "")
    if passwort == ADMIN_PASSWORT:
        session["ist_admin"] = True
        return redirect(url_for("admin_seite"))
    return render_template("admin_login.html", fehler="Falsches Passwort.")


@app.route("/admin/logout", methods=["GET", "POST"])
def admin_logout():
    session.pop("ist_admin", None)
    return redirect(url_for("admin_seite"))


@app.route("/admin/kalibrieren", methods=["POST"])
def admin_kalibrieren():
    if not ist_admin_eingeloggt():
        return redirect(url_for("admin_seite"))

    ip = request.form.get("ip")
    try:
        neuer_wert = float(request.form.get("neuer_wert", "").replace(",", "."))
    except ValueError:
        neuer_wert = None

    if ip and neuer_wert is not None:
        kalibriere_lebenszeit(ip, neuer_wert)

    return redirect(url_for("admin_seite"))


# ============================================================
#  Webseiten - liefern nur das leere HTML-Geruest,
#  Daten kommen per JS ueber /api/status bzw. /api/wasser
# ============================================================
@app.route("/")
def webseite():
    return render_template("index.html")


@app.route("/wasser")
def wasser_seite():
    return render_template("wasser.html")


# ============================================================
#  Start
# ============================================================
if __name__ == "__main__":
    print("=" * 55)
    print("  ESP32 Monitor Server")
    print("  Port: 5000")
    print("  Unterstuetzt: HC-SR04 + LJ18A3")
    print("  Frontend: fetch()-Polling (kein <meta refresh> mehr)")
    print("-" * 55)
    print("  OTA Endpunkte:")
    print("  Schall:  /firmware/schall/version")
    print("           /firmware/schall/download")
    print("  LJ18A3:  /firmware/lj18a3/version")
    print("           /firmware/lj18a3/download")
    print("-" * 55)
    print(f"  Schall  FW: {lese_version(FW_SCHALL_VER)} | "
          f"{'OK' if os.path.exists(FW_SCHALL_BIN) else 'FEHLT'}")
    print(f"  LJ18A3  FW: {lese_version(FW_LJ18A3_VER)} | "
          f"{'OK' if os.path.exists(FW_LJ18A3_BIN) else 'FEHLT'}")
    print("=" * 55)
    app.run(host="0.0.0.0", port=5000, debug=False)
