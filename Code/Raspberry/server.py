#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESP32 Monitor Server - v1.3
Laeuft auf dem Raspberry Pi (DietPi), empfaengt Daten vom ESP32
und zeigt sie auf einer Webseite an.

Changelog:
  v1.0 - Grundversion: Empfang + Webseite
  v1.1 - Online/Offline Erkennung
  v1.2 - Batteriespannung + Ladestand
  v1.3 - Display-Status wird vom ESP32 mitgesendet und angezeigt

Installation:
  sudo apt install python3-venv -y
  python3 -m venv ~/esp32-monitor/venv
  source ~/esp32-monitor/venv/bin/activate
  pip install flask
  python server.py

Autostart (systemd):
  [Unit]
  Description=ESP32 Monitor Server
  After=network.target

  [Service]
  ExecStart=/home/dietpi/esp32-monitor/venv/bin/python /home/dietpi/esp32-monitor/server.py
  WorkingDirectory=/home/dietpi/esp32-monitor
  Restart=always
  RestartSec=5
  User=root

  [Install]
  WantedBy=multi-user.target

Nach Aenderungen an dieser Datei Daemon neu starten:
  sudo systemctl restart esp32-monitor
  sudo systemctl status esp32-monitor

Endpunkte:
  GET  /          -> Webseite mit Uebersicht und Nachrichtentabelle
  POST /api/data  -> Empfaengt JSON-Daten vom ESP32
"""

from flask import Flask, request, jsonify, render_template_string
from datetime import datetime
from collections import deque
import threading

app = Flask(__name__)

# ================================================================
#  KONFIGURATION
# ================================================================
MAX_EINTRAEGE = 200     # Wie viele Nachrichten im RAM gespeichert werden
PORT          = 5000    # Port des Webservers
OFFLINE_SECS  = 30      # Sekunden bis ESP32 als offline gilt

# ================================================================
#  DATENSPEICHER (im RAM, kein DB noetig)
# ================================================================
lock      = threading.Lock()
eintraege = deque(maxlen=MAX_EINTRAEGE)
letzter   = {}

# ================================================================
#  HTML TEMPLATE
# ================================================================
HTML = """
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="5">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ESP32 Monitor</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: 'Segoe UI', Arial, sans-serif;
      background: #1a1a2e;
      color: #eee;
      padding: 20px;
    }
    h1   { color: #00d4aa; margin-bottom: 4px; font-size: 1.8em; }
    .subtitle { color: #aaa; margin-bottom: 24px; font-size: .9em; }
    .cards { display: flex; flex-wrap: wrap; gap: 16px; margin-bottom: 28px; }
    .card {
      background: #16213e;
      border-radius: 14px;
      padding: 20px 28px;
      flex: 1;
      min-width: 160px;
      text-align: center;
      box-shadow: 0 4px 20px rgba(0,0,0,.4);
    }
    .card-title { font-size: .75em; text-transform: uppercase;
                  letter-spacing: 2px; color: #888; margin-bottom: 8px; }
    .card-value { font-size: 2.0em; font-weight: bold; }
    .card-sub   { font-size: .85em; color: #aaa; margin-top: 4px; }
    .uptime   .card-value { color: #00d4aa; }
    .distanz  .card-value { color: #e8b86d; }
    .batterie .card-value { color: #a8e063; }
    .status   .card-value { color: #00ff88; font-size: 1.4em; }
    .status.offline .card-value { color: #ff6b6b; }
    .display-an  .card-value { color: #00ff88; }
    .display-aus .card-value { color: #ff6b6b; }
    .dot {
      display: inline-block; width: 10px; height: 10px;
      border-radius: 50%; margin-right: 6px;
      animation: blink 1.2s infinite;
    }
    .online  .dot { background: #00ff88; }
    .offline .dot { background: #ff6b6b; animation: none; }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.2} }
    h2 { color: #00d4aa; margin-bottom: 12px; font-size: 1.2em; }
    .table-wrap {
      background: #16213e;
      border-radius: 14px;
      overflow: hidden;
      box-shadow: 0 4px 20px rgba(0,0,0,.4);
    }
    table { width: 100%; border-collapse: collapse; font-size: .9em; }
    thead { background: #0f3460; }
    th { padding: 12px 16px; text-align: left; color: #00d4aa;
         font-weight: 600; letter-spacing: .5px; }
    td { padding: 10px 16px; border-bottom: 1px solid #1a1a2e; }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: rgba(0,212,170,.05); }
    .badge {
      display: inline-block; padding: 2px 10px; border-radius: 20px;
      font-size: .8em; font-weight: bold;
    }
    .badge-ok     { background: #00d4aa22; color: #00d4aa; }
    .badge-warn   { background: #e8b86d22; color: #e8b86d; }
    .badge-fehler { background: #ff6b6b22; color: #ff6b6b; }
    .badge-an     { background: #00ff8822; color: #00ff88; }
    .badge-aus    { background: #ff6b6b22; color: #ff6b6b; }
    .footer { margin-top: 20px; font-size: .75em; color: #444; text-align: center; }
  </style>
</head>
<body>

<h1>&#128268; ESP32 Monitor</h1>
<p class="subtitle">Raspberry Pi Empfangsserver &bull; aktualisiert alle 5s</p>

<div class="cards">

  <!-- Online/Offline Status -->
  <div class="card status {{ 'offline' if offline else 'online' }}">
    <div class="card-title">Status</div>
    <div class="card-value">
      <span class="dot"></span>
      {{ 'OFFLINE' if offline else 'ONLINE' }}
    </div>
    <div class="card-sub">
      {% if letzter %}
        Letztes Signal: {{ letzter.empfangen_um }}
      {% else %}
        Noch keine Daten
      {% endif %}
    </div>
  </div>

  <!-- Uptime -->
  <div class="card uptime">
    <div class="card-title">&#9201; ESP32 Uptime</div>
    <div class="card-value">{{ letzter.uptime if letzter else '--:--:--' }}</div>
    <div class="card-sub">seit letztem Neustart</div>
  </div>

  <!-- Distanz -->
  <div class="card distanz">
    <div class="card-title">&#128268; Distanz</div>
    <div class="card-value">
      {% if letzter %}
        {% if letzter.distanz_cm == -1 %}
          Kein Objekt
        {% else %}
          {{ letzter.distanz_cm }} cm
        {% endif %}
      {% else %}
        -- cm
      {% endif %}
    </div>
  </div>

  <!-- Batterie -->
  <div class="card batterie">
    <div class="card-title">&#128267; Batterie</div>
    <div class="card-value">{{ '%.2f V' % letzter.batterie_v if letzter else '-- V' }}</div>
    <div class="card-sub">{{ letzter.ladestand if letzter else '' }}</div>
  </div>

  <!-- Display Status -->
  <div class="card {{ 'display-an' if letzter and letzter.display_an else 'display-aus' }}">
    <div class="card-title">&#128261; Display</div>
    <div class="card-value">
      {% if letzter %}
        {{ 'AN' if letzter.display_an else 'AUS' }}
      {% else %}
        --
      {% endif %}
    </div>
    <div class="card-sub">OLED am ESP32</div>
  </div>

  <!-- Nachrichten Zaehler -->
  <div class="card">
    <div class="card-title">&#128235; Nachrichten</div>
    <div class="card-value" style="color:#a78bfa">{{ anzahl }}</div>
    <div class="card-sub">insgesamt empfangen</div>
  </div>

</div>

<!-- Nachrichten Tabelle -->
<h2>&#128203; Letzte Nachrichten</h2>
<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Empfangen um</th>
        <th>ESP32 Uptime</th>
        <th>Distanz</th>
        <th>Batterie</th>
        <th>Display</th>
        <th>ESP32 IP</th>
      </tr>
    </thead>
    <tbody>
      {% for e in eintraege %}
      <tr>
        <td style="color:#555">{{ loop.index }}</td>
        <td>{{ e.empfangen_um }}</td>
        <td><span class="badge badge-ok">{{ e.uptime }}</span></td>
        <td>
          {% if e.distanz_cm == -1 %}
            <span class="badge badge-warn">Kein Objekt</span>
          {% else %}
            {{ e.distanz_cm }} cm
          {% endif %}
        </td>
        <td>
          {% if e.batterie_v >= 12.4 %}
            <span class="badge badge-ok">{{ '%.2f' % e.batterie_v }} V</span>
          {% elif e.batterie_v >= 12.0 %}
            <span class="badge badge-warn">{{ '%.2f' % e.batterie_v }} V</span>
          {% else %}
            <span class="badge badge-fehler">{{ '%.2f' % e.batterie_v }} V</span>
          {% endif %}
        </td>
        <td>
          {% if e.display_an %}
            <span class="badge badge-an">AN</span>
          {% else %}
            <span class="badge badge-aus">AUS</span>
          {% endif %}
        </td>
        <td style="color:#888">{{ e.ip }}</td>
      </tr>
      {% else %}
      <tr>
        <td colspan="7" style="text-align:center; color:#555; padding:30px">
          Noch keine Daten empfangen...
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
</div>

<div class="footer">
  Raspberry Pi ESP32 Monitor v1.3 &bull; Port {{ port }} &bull;
  Max. {{ max_eintraege }} Eintraege im Speicher
</div>

</body>
</html>
"""

# ================================================================
#  HILFSFUNKTIONEN
# ================================================================
def ladestand(v):
    if v >= 12.7: return "100% - Voll"
    if v >= 12.4: return "75%"
    if v >= 12.2: return "50%"
    if v >= 12.0: return "25%"
    if v >= 11.8: return "Schwach!"
    return "LEER - Abschalten!"

def ist_offline():
    """ESP32 gilt als offline wenn mehr als OFFLINE_SECS Sekunden kein Signal"""
    if not letzter:
        return True
    delta = (datetime.now() - letzter["_zeitstempel"]).total_seconds()
    return delta > OFFLINE_SECS

# ================================================================
#  API ENDPUNKT - empfaengt Daten vom ESP32
# ================================================================
@app.route("/api/data", methods=["POST"])
def empfange_daten():
    global letzter

    daten = request.get_json(silent=True)
    if not daten:
        return jsonify({"fehler": "Kein JSON"}), 400

    eintrag = {
        "empfangen_um" : datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "_zeitstempel" : datetime.now(),
        "uptime"       : daten.get("uptime", "--"),
        "uptime_ms"    : daten.get("uptime_ms", 0),
        "distanz_cm"   : daten.get("distanz_cm", -1),
        "batterie_v"   : daten.get("batterie_v", 0.0),
        "display_an"   : daten.get("display_an", True),
        "ip"           : daten.get("ip", "unbekannt"),
        "ladestand"    : ladestand(daten.get("batterie_v", 0.0)),
    }

    with lock:
        eintraege.appendleft(eintrag)
        letzter = eintrag

    print("[" + eintrag["empfangen_um"] + "] "
          "Uptime=" + eintrag["uptime"] + "  "
          "Distanz=" + str(eintrag["distanz_cm"]) + "cm  "
          "Batt=" + str(round(eintrag["batterie_v"], 2)) + "V  "
          "Display=" + ("AN" if eintrag["display_an"] else "AUS"))

    return jsonify({"status": "ok"}), 200

# ================================================================
#  WEBSEITE
# ================================================================
@app.route("/")
def webseite():
    with lock:
        liste   = list(eintraege)
        aktuell = dict(letzter) if letzter else None

    return render_template_string(
        HTML,
        eintraege     = liste,
        letzter       = aktuell,
        anzahl        = len(liste),
        offline       = ist_offline(),
        port          = PORT,
        max_eintraege = MAX_EINTRAEGE,
    )

# ================================================================
#  START
# ================================================================
if __name__ == "__main__":
    print("=" * 50)
    print("  ESP32 Monitor Server v1.3")
    print("  Webseite:  http://<Pi-IP>:" + str(PORT))
    print("  API:       http://<Pi-IP>:" + str(PORT) + "/api/data")
    print("=" * 50)
    app.run(host="0.0.0.0", port=PORT, debug=False)
