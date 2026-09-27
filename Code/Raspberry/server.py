#!/usr/bin/env python3
# ============================================================
#  Raspberry Pi Flask Server - Kombiniert (v2.9)
#  Empfaengt Daten von:
#    - ESP32 Ultraschall-Monitor (Uptime_Schall.ino)  -> sensor_typ fehlt ODER "HC-SR04"
#    - ESP32 Wasser-Monitor      (Uptime_LJ18A3.ino)  -> sensor_typ = "LJ18A3"
#    - ESP32 Garage-Monitor      (Garage_Control.ino) -> sensor_typ = "Garage"
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
SERVER_VERSION = "3.0"

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
        with open(pfad, "r") as f: return f.read().strip()
    except: return "0.0"

def ist_online(device):
    letzter_kontakt = device.get("_last_seen_dt")
    if letzter_kontakt is None: return False
    return (datetime.now() - letzter_kontakt).total_seconds() <= OFFLINE_SECS

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
            with open(GARAGE_CONFIG_FILE, "r") as f: return json.load(f)
        except: pass
    return {"tor1": {"min": 10, "max": 200}, "tor2": {"min": 10, "max": 200}, "auto1": {"threshold": 150}, "auto2": {"threshold": 150}}

def save_garage_config(config):
    with open(GARAGE_CONFIG_FILE, "w") as f: json.dump(config, f)

messages = []

# ============================================================
#  API Endpunkt - Sensordaten empfangen
# ============================================================
@app.route("/api/data", methods=["POST"])
def empfange_daten():
    global messages
    try:
        daten = request.get_json(force=True)
        if not daten: return jsonify({"fehler": "Kein JSON"}), 400
        ip = daten.get("ip", request.remote_addr)
        sensor_typ = daten.get("sensor_typ", "HC-SR04")
        jetzt = datetime.now()
        now_str = jetzt.strftime("%H:%M:%S")

        with data_lock:
            details = ""
            if sensor_typ == "Garage":
                # v3.0: Garage-Steuerung implementiert
                # Existierende Befehle (cmd_trigger_tor1/2) erhalten, wenn bereits vorhanden
                existing_device = devices_garage.get(ip, {})
                devices_garage[ip] = {
                    "uptime": daten.get("uptime", "--"), "uptime_ms": daten.get("uptime_ms", 0),
                    "tor1_cm": float(daten.get("tor1_cm", -1)), "tor2_cm": float(daten.get("tor2_cm", -1)),
                    "auto1_cm": float(daten.get("auto1_cm", -1)), "auto2_cm": float(daten.get("auto2_cm", -1)),
                    "firmware": daten.get("firmware", "?"), "last_seen": now_str, "_last_seen_dt": jetzt,
                    "cmd_trigger_tor1": existing_device.get("cmd_trigger_tor1", False),
                    "cmd_trigger_tor2": existing_device.get("cmd_trigger_tor2", False)
                }
                details = f"T1: {daten.get('tor1_cm')}cm | T2: {daten.get('tor2_cm')}cm"
            elif sensor_typ == "LJ18A3":
                vorheriges = devices_lj18a3.get(ip)
                neuer_liter = float(daten.get("liter_gesamt", 0))
                momentaner_df = 0.0
                if vorheriges:
                    delta_l = neuer_liter - vorheriges.get("liter_gesamt", 0.0)
                    delta_s = (jetzt - vorheriges.get("_last_seen_dt", jetzt)).total_seconds()
                    if delta_s > 0 and delta_l >= 0: momentaner_df = (delta_l / delta_s) * 60.0
                
                v_geglaettet = vorheriges.get("durchfluss_l_min", 0.0) if vorheriges else 0.0
                df_final = round(DURCHFLUSS_GLAETTUNG * momentaner_df + (1 - DURCHFLUSS_GLAETTUNG) * v_geglaettet, 3)
                
                devices_lj18a3[ip] = {
                    "uptime": daten.get("uptime", "--"), "liter_gesamt": neuer_liter,
                    "impulse_gesamt": int(daten.get("impulse_gesamt", 0)), "batterie_v": float(daten.get("batterie_v", 0)),
                    "firmware": daten.get("firmware", "?"), "display_an": bool(daten.get("display_an", True)),
                    "durchfluss_l_min": df_final, "last_seen": now_str, "_last_seen_dt": jetzt
                }
                insert_messwert(ip, neuer_liter)
                details = f"{neuer_liter:.1f} L | {df_final:.2f} L/min"
            else:
                dist = float(daten.get("distanz_cm", -1))
                devices_schall[ip] = {
                    "uptime": daten.get("uptime", "--"), "distanz_cm": dist,
                    "batterie_v": float(daten.get("batterie_v", 0)), "firmware": daten.get("firmware", "?"),
                    "display_an": bool(daten.get("display_an", True)), "last_seen": now_str, "_last_seen_dt": jetzt
                }
                details = f"Distanz: {dist} cm"

            messages.append({"zeit": now_str, "ip": ip, "typ": sensor_typ, "details": details, 
                             "impulse_gesamt": int(daten.get("impulse_gesamt", 0)) if sensor_typ == "LJ18A3" else 0,
                             "liter_gesamt": float(daten.get("liter_gesamt", 0)) if sensor_typ == "LJ18A3" else 0.0,
                             "distanz_cm": float(daten.get("distanz_cm", -1)) if sensor_typ == "HC-SR04" else -1,
                             "batterie_v": float(daten.get("batterie_v", 0))})
            if len(messages) > 100: messages.pop(0)

        resp = {"status": "ok"}
        if sensor_typ == "Garage" and ip in devices_garage:
            for i in [1, 2]:
                if devices_garage[ip].get(f"cmd_trigger_tor{i}"):
                    resp[f"trigger_tor{i}"] = True
                    devices_garage[ip][f"cmd_trigger_tor{i}"] = False
        return jsonify(resp), 200
    except Exception as e:
        return jsonify({"fehler": str(e)}), 500

def _lj18a3_liste():
    return [{**d, "ip": ip, "online": ist_online(d), "liter_lebenszeit": hole_lebenszeit_verbrauch(ip)} 
            for ip, d in devices_lj18a3.items()]

def _garage_liste():
    return [{**d, "ip": ip, "online": ist_online(d)} for ip, d in devices_garage.items()]

def _schall_liste():
    return [{**d, "ip": ip, "online": ist_online(d)} for ip, d in devices_schall.items()]

@app.route("/api/status")
def api_status():
    with data_lock:
        lj, sc, ga = _lj18a3_liste(), _schall_liste(), _garage_liste()
        alle = lj + sc + ga
        return jsonify({
            "now": datetime.now().strftime("%d.%m.%Y %H:%M:%S"), "offline_secs": OFFLINE_SECS,
            "summary": {"gesamt": len(alle), "online": sum(1 for d in alle if d["online"]), "offline": sum(1 for d in alle if not d["online"])},
            "devices_lj18a3": lj, "devices_schall": sc, "devices_garage": ga,
            "firmware": {
                "lj18a3": {"version": lese_version(FW_LJ18A3_VER), "ok": os.path.exists(FW_LJ18A3_BIN)},
                "schall": {"version": lese_version(FW_SCHALL_VER), "ok": os.path.exists(FW_SCHALL_BIN)},
                "garage": {"version": lese_version(FW_GARAGE_VER), "ok": os.path.exists(FW_GARAGE_BIN)},
            },
            "messages": list(reversed(messages[-20:])), "server_version": SERVER_VERSION
        })

@app.route("/api/wasser")
def api_wasser():
    with data_lock:
        geraete = _lj18a3_liste()
        return jsonify({
            "now": datetime.now().strftime("%d.%m.%Y %H:%M:%S"), "offline_secs": OFFLINE_SECS,
            "geraete": geraete,
            "summary": {
                "liter_lebenszeit": round(sum(d["liter_lebenszeit"] for d in geraete), 1),
                "liter_seit_neustart": round(sum(d["liter_gesamt"] for d in geraete), 1),
                "durchfluss_l_min": round(sum(d.get("durchfluss_l_min", 0.0) for d in geraete), 3),
            },
            "server_version": SERVER_VERSION
        })

@app.route("/api/wasser/verlauf")
def api_wasser_verlauf():
    ip, zeitraum = request.args.get("ip"), request.args.get("zeitraum", "tag")
    try: anzahl = int(request.args.get("anzahl", 30))
    except: anzahl = 30
    if not ip:
        ips = liste_geraete_ips()
        if not ips: return jsonify({"labels": [], "werte": []})
        ip = ips[0]
    daten = hole_verlauf(ip, zeitraum, anzahl=anzahl)
    return jsonify({"ip": ip, "zeitraum": zeitraum, "labels": [d["label"] for d in daten], "werte": [d["liter"] for d in daten]})

@app.route("/api/garage")
def api_garage():
    with data_lock: return jsonify({"now": datetime.now().strftime("%d.%m.%Y %H:%M:%S"), "devices": _garage_liste(), "config": load_garage_config()})

@app.route("/api/garage/control", methods=["POST"])
def api_garage_control():
    data = request.get_json(); ip, tor = data.get("ip"), data.get("tor")
    with data_lock:
        if ip in devices_garage: devices_garage[ip][f"cmd_trigger_tor{tor}"] = True; return jsonify({"status": "queued"})
    return jsonify({"status": "error"}), 404

@app.route("/api/garage/calibrate", methods=["POST"])
def api_garage_calibrate():
    if not ist_admin_eingeloggt(): return jsonify({"status": "error"}), 401
    config = load_garage_config(); data = request.get_json()
    for key in ["tor1", "tor2", "auto1", "auto2"]:
        if key in data: config[key].update(data[key])
    save_garage_config(config); return jsonify({"status": "ok"})

@app.route("/")
def webseite(): return render_template("index.html")

@app.route("/wasser")
def wasser_seite(): return render_template("wasser.html")

@app.route("/garage")
def garage_seite(): return render_template("garage.html")

@app.route("/admin")
def admin_seite():
    if not ist_admin_eingeloggt(): return render_template("admin_login.html")
    with data_lock: return render_template("admin.html", geraete=_lj18a3_liste(), garage_config=load_garage_config())

@app.route("/admin/login", methods=["POST"])
def admin_login():
    if request.form.get("passwort") == ADMIN_PASSWORT:
        session["ist_admin"] = True
        return redirect(url_for("admin_seite"))
    return render_template("admin_login.html", fehler="Falsch")

@app.route("/admin/logout")
def admin_logout():
    session.pop("ist_admin", None); return redirect(url_for("admin_seite"))

@app.route("/admin/kalibrieren", methods=["POST"])
def admin_kalibrieren():
    if not ist_admin_eingeloggt(): return redirect(url_for("admin_seite"))
    ip = request.form.get("ip")
    try: val = float(request.form.get("neuer_wert", "").replace(",", "."))
    except: val = None
    if ip and val is not None: kalibriere_lebenszeit(ip, val)
    return redirect(url_for("admin_seite"))

@app.route("/firmware/<typ>/version")
def fw_version(typ):
    p = {"schall": FW_SCHALL_VER, "lj18a3": FW_LJ18A3_VER, "garage": FW_GARAGE_VER}.get(typ)
    return jsonify({"version": lese_version(p), "typ": typ})

@app.route("/firmware/<typ>/download")
def fw_download(typ):
    p = {"schall": FW_SCHALL_BIN, "lj18a3": FW_LJ18A3_BIN, "garage": FW_GARAGE_BIN}.get(typ)
    if not os.path.exists(p): return "FEHLT", 404
    return send_file(p, mimetype="application/octet-stream", as_attachment=True, download_name=f"firmware_{typ}.bin")

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False)
