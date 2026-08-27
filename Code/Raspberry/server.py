#!/usr/bin/env python3
# ============================================================
#  Raspberry Pi Flask Server - Kombiniert
#  Empfaengt Daten von:
#    - ESP32 Ultraschall-Monitor (Uptime_Schall.ino)  -> sensor_typ fehlt ODER "HC-SR04"
#    - ESP32 Wasser-Monitor      (Uptime_LJ18A3.ino)  -> sensor_typ = "LJ18A3"
#    - ESP32 Garage-Monitor      (Garage_Control.ino) -> sensor_typ = "Garage"
#
#  v2.8 - Garage Integration (2 Tore, 2 Autos, 2 Relais)
# ============================================================

from flask import Flask, request, jsonify, render_template, send_file, session, redirect, url_for
from datetime import datetime
import threading
import os
import secrets
import json

from wasserdb import init_db
from wasserdb.rollup import starte_rollup_thread
from wasserdb.queries import (
    insert_messwert,
    liste_geraete_ips,
    hole_verlauf,
    hole_lebenszeit_verbrauch,
    kalibriere_lebenszeit,
)

app = Flask(__name__, template_folder="templates", static_folder="static")
app.secret_key = secrets.token_hex(32)
data_lock = threading.Lock()

ADMIN_PASSWORT = "aendere-mich"

init_db()
starte_rollup_thread()

def ist_admin_eingeloggt():
    return session.get("ist_admin", False) is True

@app.context_processor
def inject_server_version():
    return dict(server_version=SERVER_VERSION)

OFFLINE_SECS = 30
DURCHFLUSS_GLAETTUNG = 0.3
SERVER_VERSION = "2.8"

# ============================================================
#  Firmware Pfade
# ============================================================
BASE_DIR         = os.path.dirname(os.path.abspath(__file__))
FW_SCHALL_DIR    = os.path.join(BASE_DIR, "firmware", "schall")
FW_LJ18A3_DIR    = os.path.join(BASE_DIR, "firmware", "lj18a3")
FW_GARAGE_DIR    = os.path.join(BASE_DIR, "firmware", "garage")
FW_SCHALL_BIN    = os.path.join(FW_SCHALL_DIR, "firmware.bin")
FW_LJ18A3_BIN    = os.path.join(FW_LJ18A3_DIR, "firmware.bin")
FW_GARAGE_BIN    = os.path.join(FW_GARAGE_DIR, "firmware.bin")
FW_SCHALL_VER    = os.path.join(FW_SCHALL_DIR, "version.txt")
FW_LJ18A3_VER    = os.path.join(FW_LJ18A3_DIR, "version.txt")
FW_GARAGE_VER    = os.path.join(FW_GARAGE_DIR, "version.txt")

os.makedirs(FW_SCHALL_DIR, exist_ok=True)
os.makedirs(FW_LJ18A3_DIR, exist_ok=True)
os.makedirs(FW_GARAGE_DIR, exist_ok=True)

def lese_version(pfad):
    try:
        with open(pfad, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "0.0"

def ist_online(device):
    letzter_kontakt = device.get("_last_seen_dt")
    if letzter_kontakt is None:
        return False
    delta = (datetime.now() - letzter_kontakt).total_seconds()
    return delta <= OFFLINE_SECS

# ============================================================
#  Geraete-Datenspeicher
# ============================================================
devices_schall = {}
devices_lj18a3 = {}
devices_garage = {}

GARAGE_CONFIG_FILE = os.path.join(BASE_DIR, "garage_config.json")

def load_garage_config():
    if os.path.exists(GARAGE_CONFIG_FILE):
        try:
            with open(GARAGE_CONFIG_FILE, "r") as f:
                return json.load(f)
        except:
            pass
    return {
        "tor1": {"min": 10, "max": 200},
        "tor2": {"min": 10, "max": 200},
        "auto1": {"threshold": 150},
        "auto2": {"threshold": 150}
    }

def save_garage_config(config):
    with open(GARAGE_CONFIG_FILE, "w") as f:
        json.dump(config, f)

messages = []

# ============================================================
#  API Endpunkt - Sensordaten empfangen
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
            if sensor_typ == "Garage":
                devices_garage[ip] = {
                    "uptime":     daten.get("uptime", "--"),
                    "uptime_ms":  daten.get("uptime_ms", 0),
                    "tor1_cm":    float(daten.get("tor1_cm", -1)),
                    "tor2_cm":    float(daten.get("tor2_cm", -1)),
                    "auto1_cm":   float(daten.get("auto1_cm", -1)),
                    "auto2_cm":   float(daten.get("auto2_cm", -1)),
                    "relais1":    bool(daten.get("relais1", False)),
                    "relais2":    bool(daten.get("relais2", False)),
                    "firmware":   daten.get("firmware", "?"),
                    "last_seen":  now_str,
                    "_last_seen_dt": jetzt,
                }
                details = (f"T1: {daten.get('tor1_cm')}cm | T2: {daten.get('tor2_cm')}cm | "
                           f"A1: {daten.get('auto1_cm')}cm | A2: {daten.get('auto2_cm')}cm")
            elif sensor_typ == "LJ18A3":
                vorheriges = devices_lj18a3.get(ip)
                neuer_liter_gesamt = float(daten.get("liter_gesamt", 0))
                momentaner_durchfluss = 0.0
                if vorheriges is not None:
                    delta_liter = neuer_liter_gesamt - vorheriges.get("liter_gesamt", 0.0)
                    delta_sek   = (jetzt - vorheriges.get("_last_seen_dt", jetzt)).total_seconds()
                    if delta_sek > 0 and delta_liter >= 0:
                        momentaner_durchfluss = (delta_liter / delta_sek) * 60.0

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
                    "_last_seen_dt": jetzt,
                }
                details = (f"Distanz: {daten.get('distanz_cm', -1)} cm | "
                           f"Batt: {daten.get('batterie_v', 0):.2f}V | "
                           f"FW: v{daten.get('firmware', '?')}")

            messages.append({
                "zeit":           now_str,
                "ip":             ip,
                "typ":            sensor_typ,
                "details":        details,
                "impulse_gesamt": int(daten.get("impulse_gesamt", 0)) if sensor_typ == "LJ18A3" else 0,
                "liter_gesamt":   float(daten.get("liter_gesamt", 0)) if sensor_typ == "LJ18A3" else 0.0,
                "distanz_cm":     float(daten.get("distanz_cm", -1)) if sensor_typ == "HC-SR04" else -1,
                "batterie_v":     float(daten.get("batterie_v", 0)),
            })
            if len(messages) > 100:
                messages = messages[-100:]

        print(f"[{now_str}] {sensor_typ} von {ip}: {details}")
        
        # Check for queued commands
        response_data = {"status": "ok"}
        with data_lock:
            if sensor_typ == "Garage" and ip in devices_garage:
                if devices_garage[ip].get("cmd_trigger_tor1"):
                    response_data["trigger_tor1"] = True
                    devices_garage[ip]["cmd_trigger_tor1"] = False
                if devices_garage[ip].get("cmd_trigger_tor2"):
                    response_data["trigger_tor2"] = True
                    devices_garage[ip]["cmd_trigger_tor2"] = False
        
        return jsonify(response_data), 200

    except Exception as e:
        print(f"Fehler beim Verarbeiten: {e}")
        return jsonify({"fehler": str(e)}), 500

def _lj18a3_liste():
    liste = []
    for ip, d in devices_lj18a3.items():
        d2 = {k: v for k, v in d.items() if k != "_last_seen_dt"}
        d2["ip"] = ip
        d2["online"] = ist_online(d)
        d2["liter_lebenszeit"] = hole_lebenszeit_verbrauch(ip)
        liste.append(d2)
    return liste

def _garage_liste():
    liste = []
    for ip, d in devices_garage.items():
        d2 = {k: v for k, v in d.items() if k != "_last_seen_dt"}
        d2["ip"] = ip
        d2["online"] = ist_online(d)
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

@app.route("/api/status")
def api_status():
    with data_lock:
        lj_liste = _lj18a3_liste()
        sc_liste = _schall_liste()
        ga_liste = _garage_liste()
        alle = lj_liste + sc_liste + ga_liste
        return jsonify({
            "now": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "offline_secs": OFFLINE_SECS,
            "summary": {"gesamt": len(alle), "online": sum(1 for d in alle if d["online"]), "offline": sum(1 for d in alle if not d["online"])},
            "devices_lj18a3": lj_liste,
            "devices_schall": sc_liste,
            "devices_garage": ga_liste,
            "firmware": {
                "lj18a3": {"version": lese_version(FW_LJ18A3_VER), "ok": os.path.exists(FW_LJ18A3_BIN)},
                "schall": {"version": lese_version(FW_SCHALL_VER), "ok": os.path.exists(FW_SCHALL_BIN)},
                "garage": {"version": lese_version(FW_GARAGE_VER), "ok": os.path.exists(FW_GARAGE_BIN)},
            },
            "messages": list(reversed(messages[-20:])),
            "server_version": SERVER_VERSION,
        })

@app.route("/garage")
def garage_seite():
    return render_template("garage.html")

@app.route("/api/garage")
def api_garage():
    with data_lock:
        return jsonify({
            "now": datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
            "devices": _garage_liste(),
            "config": load_garage_config()
        })

@app.route("/api/garage/control", methods=["POST"])
def api_garage_control():
    data = request.get_json()
    ip = data.get("ip")
    tor = data.get("tor")
    with data_lock:
        if ip in devices_garage:
            devices_garage[ip][f"cmd_trigger_tor{tor}"] = True
            return jsonify({"status": "queued"})
    return jsonify({"status": "error", "message": "Device not found"}), 404

@app.route("/api/garage/calibrate", methods=["POST"])
def api_garage_calibrate():
    if not ist_admin_eingeloggt():
        return jsonify({"status": "error", "message": "Unauthorized"}), 401
    config = load_garage_config()
    data = request.get_json()
    for key in ["tor1", "tor2", "auto1", "auto2"]:
        if key in data:
            config[key].update(data[key])
    save_garage_config(config)
    return jsonify({"status": "ok"})

@app.route("/")
def webseite():
    return render_template("index.html")

@app.route("/wasser")
def wasser_seite():
    return render_template("wasser.html")

@app.route("/admin", methods=["GET"])
def admin_seite():
    if not ist_admin_eingeloggt():
        return render_template("admin_login.html")
    with data_lock:
        geraete = _lj18a3_liste()
        garage_config = load_garage_config()
    return render_template("admin.html", geraete=geraete, garage_config=garage_config)

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

@app.route("/firmware/schall/version", methods=["GET"])
def fw_schall_version():
    return jsonify({"version": lese_version(FW_SCHALL_VER), "typ": "HC-SR04"}), 200

@app.route("/firmware/schall/download", methods=["GET"])
def fw_schall_download():
    if not os.path.exists(FW_SCHALL_BIN): return "Keine Schall-Firmware vorhanden", 404
    return send_file(FW_SCHALL_BIN, mimetype="application/octet-stream", as_attachment=True, download_name="firmware_schall.bin")

@app.route("/firmware/lj18a3/version", methods=["GET"])
def fw_lj18a3_version():
    return jsonify({"version": lese_version(FW_LJ18A3_VER), "typ": "LJ18A3"}), 200

@app.route("/firmware/lj18a3/download", methods=["GET"])
def fw_lj18a3_download():
    if not os.path.exists(FW_LJ18A3_BIN): return "Keine LJ18A3-Firmware vorhanden", 404
    return send_file(FW_LJ18A3_BIN, mimetype="application/octet-stream", as_attachment=True, download_name="firmware_lj18a3.bin")

@app.route("/firmware/garage/version", methods=["GET"])
def fw_garage_version():
    return jsonify({"version": lese_version(FW_GARAGE_VER), "typ": "Garage"}), 200

@app.route("/firmware/garage/download", methods=["GET"])
def fw_garage_download():
    if not os.path.exists(FW_GARAGE_BIN): return "Keine Garage-Firmware vorhanden", 404
    return send_file(FW_GARAGE_BIN, mimetype="application/octet-stream", as_attachment=True, download_name="firmware_garage.bin")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
