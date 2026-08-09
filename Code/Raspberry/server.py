#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ESP32 Monitor Server - v2.0
Laeuft auf dem Raspberry Pi (DietPi), empfaengt Daten von MEHREREN ESP32 Boards
und zeigt sie auf einer Webseite an. Jedes Board bekommt eine eigene Status-Karte.

Changelog:
  v1.0 - Grundversion: Empfang + Webseite
  v1.1 - Online/Offline Erkennung
  v1.2 - Batteriespannung + Ladestand
  v1.3 - Display-Status wird vom ESP32 mitgesendet und angezeigt
  v2.0 - Multi-ESP32 Support: Jedes Board bekommt eigene Status-Karte

Installation:
  sudo apt install python3-venv -y
  python3 -m venv ~/esp32-monitor/venv
  source ~/esp32-monitor/venv/bin/activate
  pip install flask
  python server.py

Nach Aenderungen neu starten:
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
MAX_EINTRAEGE = 200     # Wie viele Nachrichten insgesamt gespeichert werden
PORT          = 5000    # Port des Webservers
OFFLINE_SECS  = 30      # Sekunden bis ein ESP32 als offline gilt

# ================================================================
#  DATENSPEICHER
# ================================================================
lock      = threading.Lock()
eintraege = deque(maxlen=MAX_EINTRAEGE)   # Alle Nachrichten aller Boards

# Pro Board wird der letzte Datensatz gespeichert:
# boards = { "192.168.178.84": { ...letzter Eintrag... }, ... }
boards = {}

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
    h2   { color: #00d4aa; margin-bottom: 12px; font-size: 1.2em; margin-top: 28px; }
    .subtitle { color: #aaa; margin-bottom: 24px; font-size: .9em; }

    /* ── Board-Sektion ── */
    .board-section {
      background: #16213e;
      border-radius: 16px;
      padding: 20px 24px;
      margin-bottom: 20px;
      box-shadow: 0 4px 20px rgba(0,0,0,.4);
      border-left: 4px solid #0f3460;
    }
    .board-section.online  { border-left-color: #00d4aa; }
    .board-section.offline { border-left-color: #ff6b6b; }

    .board-header {
      display: flex;
      align-items: center;
      gap: 12px;
      margin-bottom: 16px;
      flex-wrap: wrap;
    }
    .board-title {
      font-size: 1.1em;
      font-weight: bold;
      color: #eee;
    }
    .board-ip {
      font-size: .85em;
      color: #888;
      font-family: monospace;
    }
    .board-last-seen {
      font-size: .8em;
      color: #666;
      margin-left: auto;
    }

    /* Status Badge */
    .status-badge {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 12px;
      border-radius: 20px;
      font-size: .8em;
      font-weight: bold;
    }
    .status-badge.online  { background: #00d4aa22; color: #00d4aa; }
    .status-badge.offline { background: #ff6b6b22; color: #ff6b6b; }
    .dot {
      width: 8px; height: 8px;
      border-radius: 50%;
      display: inline-block;
    }
    .online  .dot { background: #00ff88; animation: blink 1.2s infinite; }
    .offline .dot { background: #ff6b6b; }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.2} }

    /* Mini-Karten pro Board */
    .mini-cards {
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }
    .mini-card {
      background: #0f3460;
      border-radius: 10px;
      padding: 12px 20px;
      min-width: 130px;
      text-align: center;
      flex: 1;
    }
    .mini-card-title {
      font-size: .7em;
      text-transform: uppercase;
      letter-spacing: 1.5px;
      color: #888;
      margin-bottom: 6px;
    }
    .mini-card-value {
      font-size: 1.6em;
      font-weight: bold;
    }
    .mini-card-sub { font-size: .75em; color: #888; margin-top: 3px; }
    .col-uptime   { color: #00d4aa; }
    .col-distanz  { color: #e8b86d; }
    .col-batterie { color: #a8e063; }
    .col-display-an  { color: #00ff88; }
    .col-display-aus { color: #ff6b6b; }

    /* Zusammenfassung oben */
    .summary {
      display: flex;
      gap: 16px;
      margin-bottom: 24px;
      flex-wrap: wrap;
    }
    .summary-card {
      background: #16213e;
      border-radius: 12px;
      padding: 14px 24px;
      text-align: center;
      flex: 1;
      min-width: 120px;
      box-shadow: 0 4px 16px rgba(0,0,0,.3);
    }
    .summary-card-title { font-size: .75em; color: #888;
                          text-transform: uppercase; letter-spacing: 1.5px; }
    .summary-card-value { font-size: 2em; font-weight: bold; margin-top: 4px; }
    .col-total   { color: #a78bfa; }
    .col-online  { color: #00d4aa; }
    .col-offline { color: #ff6b6b; }

    /* Nachrichten-Tabelle */
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
    .ip-tag {
      display: inline-block; padding: 2px 8px; border-radius: 6px;
      font-size: .8em; font-family: monospace;
      background: #0f346044; color: #aaa;
    }

    .footer { margin-top: 20px; font-size: .75em; color: #444; text-align: center; }
  </style>
</head>
<body>

<h1>&#128268; ESP32 Multi-Board Monitor</h1>
<p class="subtitle">Raspberry Pi Empfangsserver v2.0 &bull; aktualisiert alle 5s</p>

<!-- Zusammenfassung -->
<div class="summary">
  <div class="summary-card">
    <div class="summary-card-title">&#128268; Boards gesamt</div>
    <div class="summary-card-value col-total">{{ boards|length }}</div>
  </div>
  <div class="summary-card">
    <div class="summary-card-title">&#128994; Online</div>
    <div class="summary-card-value col-online">{{ boards.values()|selectattr('online')|list|length }}</div>
  </div>
  <div class="summary-card">
    <div class="summary-card-title">&#128308; Offline</div>
    <div class="summary-card-value col-offline">{{ boards.values()|rejectattr('online')|list|length }}</div>
  </div>
  <div class="summary-card">
    <div class="summary-card-title">&#128235; Nachrichten</div>
    <div class="summary-card-value col-total">{{ anzahl }}</div>
  </div>
</div>

<!-- Pro Board eine Sektion -->
<h2>&#128268; Board Status</h2>

{% if boards %}
  {% for ip, board in boards.items() %}
  <div class="board-section {{ 'online' if board.online else 'offline' }}">

    <div class="board-header">
      <span class="status-badge {{ 'online' if board.online else 'offline' }}">
        <span class="dot"></span>
        {{ 'ONLINE' if board.online else 'OFFLINE' }}
      </span>
      <span class="board-title">ESP32 &mdash; {{ board.name }}</span>
      <span class="board-ip">{{ ip }}</span>
      <span class="board-last-seen">
        Letztes Signal: {{ board.empfangen_um }}
      </span>
    </div>

    <div class="mini-cards">

      <!-- Uptime -->
      <div class="mini-card">
        <div class="mini-card-title">&#9201; Uptime</div>
        <div class="mini-card-value col-uptime">{{ board.uptime }}</div>
        <div class="mini-card-sub">seit Neustart</div>
      </div>

      <!-- Distanz -->
      <div class="mini-card">
        <div class="mini-card-title">&#128268; Distanz</div>
        <div class="mini-card-value col-distanz">
          {% if board.distanz_cm == -1 %}
            Kein Obj.
          {% else %}
            {{ board.distanz_cm }} cm
          {% endif %}
        </div>
      </div>

      <!-- Batterie -->
      <div class="mini-card">
        <div class="mini-card-title">&#128267; Batterie</div>
        <div class="mini-card-value col-batterie">
          {{ '%.2f' % board.batterie_v }} V
        </div>
        <div class="mini-card-sub">{{ board.ladestand }}</div>
      </div>

      <!-- Display -->
      <div class="mini-card">
        <div class="mini-card-title">&#128261; Display</div>
        <div class="mini-card-value {{ 'col-display-an' if board.display_an else 'col-display-aus' }}">
          {{ 'AN' if board.display_an else 'AUS' }}
        </div>
      </div>

    </div>
  </div>
  {% endfor %}

{% else %}
  <div class="board-section">
    <p style="color:#555; text-align:center; padding:20px">
      Noch keine Daten empfangen...
    </p>
  </div>
{% endif %}

<!-- Nachrichten-Tabelle -->
<h2>&#128203; Letzte Nachrichten (alle Boards)</h2>
<div class="table-wrap">
  <table>
    <thead>
      <tr>
        <th>#</th>
        <th>Empfangen um</th>
        <th>Board IP</th>
        <th>ESP32 Uptime</th>
        <th>Distanz</th>
        <th>Batterie</th>
        <th>Display</th>
      </tr>
    </thead>
    <tbody>
      {% for e in eintraege %}
      <tr>
        <td style="color:#555">{{ loop.index }}</td>
        <td>{{ e.empfangen_um }}</td>
        <td><span class="ip-tag">{{ e.ip }}</span></td>
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
  Raspberry Pi ESP32 Multi-Board Monitor v2.0 &bull; Port {{ port }} &bull;
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

def board_name(ip):
    """Kurzname fuer ein Board anhand der IP - letzte Stelle der IP"""
    try:
        return "Board-" + ip.split(".")[-1]
    except:
        return "Board-???"

def ist_online(board):
    """Board gilt als online wenn weniger als OFFLINE_SECS Sekunden vergangen"""
    delta = (datetime.now() - board["_zeitstempel"]).total_seconds()
    return delta <= OFFLINE_SECS

# ================================================================
#  API ENDPUNKT - empfaengt Daten von ESP32 Boards
# ================================================================
@app.route("/api/data", methods=["POST"])
def empfange_daten():
    global boards

    daten = request.get_json(silent=True)
    if not daten:
        return jsonify({"fehler": "Kein JSON"}), 400

    # IP des sendenden Boards bestimmen
    # Zuerst aus dem JSON, dann aus dem Request
    ip = daten.get("ip", request.remote_addr or "unbekannt")

    eintrag = {
        "empfangen_um" : datetime.now().strftime("%d.%m.%Y %H:%M:%S"),
        "_zeitstempel" : datetime.now(),
        "uptime"       : daten.get("uptime", "--"),
        "uptime_ms"    : daten.get("uptime_ms", 0),
        "distanz_cm"   : daten.get("distanz_cm", -1),
        "batterie_v"   : daten.get("batterie_v", 0.0),
        "display_an"   : daten.get("display_an", True),
        "kali_faktor"  : daten.get("kali_faktor", 1.05),
        "ip"           : ip,
        "name"         : board_name(ip),
        "ladestand"    : ladestand(daten.get("batterie_v", 0.0)),
        "online"       : True,
    }

    with lock:
        # Globale Nachrichtenliste (alle Boards gemischt)
        eintraege.appendleft(eintrag)

        # Board-spezifischen Eintrag aktualisieren
        boards[ip] = eintrag

    print("[" + eintrag["empfangen_um"] + "] "
          "[" + ip + "] "
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
        liste        = list(eintraege)
        boards_aktuell = {}
        for ip, board in boards.items():
            b = dict(board)
            b["online"] = ist_online(board)
            boards_aktuell[ip] = b

    return render_template_string(
        HTML,
        eintraege     = liste,
        boards        = boards_aktuell,
        anzahl        = len(liste),
        port          = PORT,
        max_eintraege = MAX_EINTRAEGE,
    )

# ================================================================
#  START
# ================================================================
if __name__ == "__main__":
    print("=" * 50)
    print("  ESP32 Multi-Board Monitor Server v2.0")
    print("  Webseite:  http://<Pi-IP>:" + str(PORT))
    print("  API:       http://<Pi-IP>:" + str(PORT) + "/api/data")
    print("  Offline nach: " + str(OFFLINE_SECS) + " Sekunden ohne Signal")
    print("=" * 50)
    app.run(host="0.0.0.0", port=PORT, debug=False)
