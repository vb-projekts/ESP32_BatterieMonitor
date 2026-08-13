#!/usr/bin/env python3
# ============================================================
#  Raspberry Pi Flask Server - Kombiniert
#  Empfängt Daten von:
#    - ESP32 Ultraschall-Monitor (Uptime_Schall.ino)  -> sensor_typ fehlt ODER "HC-SR04"
#    - ESP32 Wasser-Monitor      (Uptime_LJ18A3.ino)  -> sensor_typ = "LJ18A3"
#
#  Beide Geräte können gleichzeitig Daten senden.
#  Webseite zeigt alle Geräte in getrennten Tabellen an.
#
#  OTA Firmware Update Endpunkte (GETRENNT pro Typ!):
#    Schall:  GET /firmware/schall/version   -> aktuelle Version
#             GET /firmware/schall/download  -> .bin Datei
#    LJ18A3:  GET /firmware/lj18a3/version   -> aktuelle Version
#             GET /firmware/lj18a3/download  -> .bin Datei
#
#  Firmware .bin Dateien ablegen in:
#    ~/esp32-monitor/firmware/schall/firmware.bin
#    ~/esp32-monitor/firmware/lj18a3/firmware.bin
#
#  Versionsdateien ablegen in:
#    ~/esp32-monitor/firmware/schall/version.txt  (Inhalt z.B.: 1.6)
#    ~/esp32-monitor/firmware/lj18a3/version.txt  (Inhalt z.B.: 1.6)
#
#  Start:  python server.py
#  Port:   5000
# ============================================================

from flask import Flask, request, jsonify, render_template_string, send_file
from datetime import datetime
import threading
import os

app = Flask(__name__)
data_lock = threading.Lock()

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

# Ordner anlegen falls nicht vorhanden
os.makedirs(FW_SCHALL_DIR, exist_ok=True)
os.makedirs(FW_LJ18A3_DIR, exist_ok=True)

def lese_version(pfad):
    """Liest Versionsnummer aus Textdatei, gibt '0.0' zurück falls nicht vorhanden."""
    try:
        with open(pfad, "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return "0.0"

# ============================================================
#  Geräte-Datenspeicher - getrennt nach Sensor-Typ
#  Schlüssel = IP-Adresse des ESP32
# ============================================================
devices_schall = {}   # HC-SR04 Ultraschall Geräte
devices_lj18a3 = {}   # LJ18A3 Wasser-Monitor Geräte

# Nachrichten-Log (letzte 100 Einträge)
messages = []

# ============================================================
#  HTML Template
# ============================================================
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta http-equiv="refresh" content="5">
    <title>ESP32 Monitor</title>
    <style>
        body {
            font-family: Arial, sans-serif;
            background: #1a1a2e;
            color: #eee;
            margin: 20px;
        }
        h1 { color: #00d4ff; }
        h2 { color: #00d4ff; margin-top: 30px; border-bottom: 1px solid #00d4ff; padding-bottom: 5px; }
        h2.water { color: #00ff99; border-bottom-color: #00ff99; }
        h2.firmware { color: #a78bfa; border-bottom-color: #a78bfa; }

        table {
            width: 100%;
            border-collapse: collapse;
            margin-top: 10px;
            background: #16213e;
            border-radius: 8px;
            overflow: hidden;
        }
        th {
            background: #0f3460;
            padding: 10px 12px;
            text-align: left;
            font-size: 0.85em;
            color: #aaa;
        }
        td {
            padding: 10px 12px;
            border-bottom: 1px solid #0f3460;
            font-size: 0.95em;
        }
        tr:last-child td { border-bottom: none; }
        tr:hover td { background: #1e3a5f; }

        .value-blue  { color: #00d4ff; font-weight: bold; }
        .value-green { color: #00ff99; font-weight: bold; }
        .value-warn  { color: #ff6b6b; font-weight: bold; }
        .value-ok    { color: #00ff99; }
        .value-purple { color: #a78bfa; font-weight: bold; }

        .badge {
            display: inline-block;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 0.8em;
            font-weight: bold;
        }
        .badge-schall { background: #0f3460; color: #00d4ff; }
        .badge-wasser { background: #0f4030; color: #00ff99; }

        .fw-box {
            background: #16213e;
            border-radius: 8px;
            padding: 16px 20px;
            margin-top: 10px;
            border-left: 4px solid #a78bfa;
            font-size: 0.9em;
        }
        .fw-box code {
            background: #0f3460;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.9em;
            color: #a78bfa;
        }
        .fw-ok   { color: #00ff99; }
        .fw-miss { color: #ff6b6b; }

        .no-data {
            color: #555;
            font-style: italic;
            padding: 15px;
        }
        .timestamp { color: #888; font-size: 0.8em; }
        .footer { color: #555; font-size: 0.8em; margin-top: 20px; }
    </style>
</head>
<body>
    <h1>&#128421;&#65039; ESP32 Monitor - Übersicht</h1>
    <p class="timestamp">Letzte Aktualisierung: {{ now }} &nbsp;|&nbsp; Auto-Refresh alle 5 Sekunden</p>

    <!-- ==================== WASSER-MONITOR ==================== -->
    <h2 class="water">&#128167; Wasser-Monitor (LJ18A3 Induktiv)</h2>
    {% if devices_lj18a3 %}
    <table>
        <tr>
            <th>IP-Adresse</th>
            <th>Uptime</th>
            <th>Verbrauch Gesamt</th>
            <th>Verbrauch Session</th>
            <th>Impulse</th>
            <th>Batterie</th>
            <th>Firmware</th>
            <!-- Spalte: Display-Status (AN/AUS) vom Board -->
            <th>Display</th>
            <th>Letztes Update</th>
        </tr>
        {% for ip, d in devices_lj18a3.items() %}
        <tr>
            <td>
                <a href="http://{{ ip }}" target="_blank" style="color:#00ff99;">{{ ip }}</a>
                <span class="badge badge-wasser">LJ18A3</span>
            </td>
            <td class="value-green">{{ d.uptime }}</td>
            <td class="value-green">{{ "%.1f"|format(d.liter_gesamt) }} L</td>
            <td>{{ "%.1f"|format(d.liter_session) }} L</td>
            <td>{{ d.impulse_gesamt }}</td>
            <td class="{{ 'value-warn' if d.batterie_v < 12.0 else 'value-ok' }}">
                {{ "%.2f"|format(d.batterie_v) }} V
            </td>
            <td class="value-purple">v{{ d.firmware }}</td>
            <!-- Display-Status: AN (grün) oder AUS (grau) -->
            {% if d.display_an %}
                <td style="color:#00ff99; font-weight:bold;">&#128994; AN</td>
            {% else %}
                <td style="color:#888;">&#9898; AUS</td>
            {% endif %}
            <td class="timestamp">{{ d.last_seen }}</td>
        </tr>
        {% endfor %}
    </table>
    {% else %}
    <p class="no-data">Noch keine Daten von Wasser-Monitor Geräten empfangen...</p>
    {% endif %}

    <!-- ==================== ULTRASCHALL-MONITOR ==================== -->
    <h2>&#128225; Ultraschall-Monitor (HC-SR04)</h2>
    {% if devices_schall %}
    <table>
        <tr>
            <th>IP-Adresse</th>
            <th>Uptime</th>
            <th>Distanz</th>
            <th>Batterie</th>
            <th>Firmware</th>
            <!-- Spalte: Display-Status (AN/AUS) vom Board -->
            <th>Display</th>
            <th>Letztes Update</th>
        </tr>
        {% for ip, d in devices_schall.items() %}
        <tr>
            <td>
                <a href="http://{{ ip }}" target="_blank" style="color:#00d4ff;">{{ ip }}</a>
                <span class="badge badge-schall">HC-SR04</span>
            </td>
            <td class="value-blue">{{ d.uptime }}</td>
            <td class="value-blue">
                {% if d.distanz_cm == -1 %}
                    <span style="color:#888;">kein Objekt</span>
                {% else %}
                    {{ "%.1f"|format(d.distanz_cm) }} cm
                {% endif %}
            </td>
            <td class="{{ 'value-warn' if d.batterie_v < 12.0 else 'value-ok' }}">
                {{ "%.2f"|format(d.batterie_v) }} V
            </td>
            <td class="value-purple">v{{ d.firmware }}</td>
            <!-- Display-Status: AN (grün) oder AUS (grau) -->
            {% if d.display_an %}
                <td style="color:#00ff99; font-weight:bold;">&#128994; AN</td>
            {% else %}
                <td style="color:#888;">&#9898; AUS</td>
            {% endif %}
            <td class="timestamp">{{ d.last_seen }}</td>
        </tr>
        {% endfor %}
    </table>
    {% else %}
    <p class="no-data">Noch keine Daten von Ultraschall Geräten empfangen...</p>
    {% endif %}

    <!-- ==================== FIRMWARE STATUS ==================== -->
    <h2 class="firmware">&#128257; Firmware Status</h2>
    <div class="fw-box">
        <p>
            <strong style="color:#00ff99;">LJ18A3 Firmware:</strong>
            Version <code>{{ fw_lj18a3_ver }}</code> &nbsp;|&nbsp;
            {% if fw_lj18a3_ok %}
                <span class="fw-ok">&#10003; firmware.bin vorhanden</span>
            {% else %}
                <span class="fw-miss">&#10005; firmware.bin FEHLT</span>
            {% endif %}
            &nbsp;|&nbsp; Endpunkte:
            <code>/firmware/lj18a3/version</code>
            <code>/firmware/lj18a3/download</code>
        </p>
        <p>
            <strong style="color:#00d4ff;">Schall Firmware:</strong>
            Version <code>{{ fw_schall_ver }}</code> &nbsp;|&nbsp;
            {% if fw_schall_ok %}
                <span class="fw-ok">&#10003; firmware.bin vorhanden</span>
            {% else %}
                <span class="fw-miss">&#10005; firmware.bin FEHLT</span>
            {% endif %}
            &nbsp;|&nbsp; Endpunkte:
            <code>/firmware/schall/version</code>
            <code>/firmware/schall/download</code>
        </p>
        <p style="color:#555; font-size:0.85em; margin-top:10px;">
            Firmware .bin ablegen in: <code>firmware/lj18a3/firmware.bin</code> bzw.
            <code>firmware/schall/firmware.bin</code> &nbsp;|&nbsp;
            Version in: <code>firmware/lj18a3/version.txt</code> bzw.
            <code>firmware/schall/version.txt</code>
        </p>
    </div>

    <!-- ==================== NACHRICHTEN LOG ==================== -->
    <h2>&#128203; Letzte Nachrichten (alle Geräte)</h2>
    <table>
        <tr>
            <th>Zeit</th>
            <th>IP</th>
            <th>Typ</th>
            <th>Details</th>
            <th>Impulse</th>
            <th>Verbrauch Gesamt</th>
            <th>Verbrauch Session</th>
            <th>Distanz</th>
            <th>Batterie</th>
        </tr>
        {% for msg in messages[-20:]|reverse %}
        <tr>
            <td class="timestamp">{{ msg.zeit }}</td>
            <td>{{ msg.ip }}</td>
            <!-- Spalte 3: Typ mit Badge -->
            <td>
                {% if msg.typ == 'LJ18A3' %}
                    <span class="badge badge-wasser">LJ18A3</span>
                {% else %}
                    <span class="badge badge-schall">HC-SR04</span>
                {% endif %}
            </td>
            <!-- Spalte 4: Details als kompakter Text -->
            <td style="font-size: 0.85em; color: #aaa;">{{ msg.details }}</td>
            
            {% if msg.typ == 'LJ18A3' %}
                <!-- LJ18A3: Wasserverbrauch-Felder befüllen; Distanz ist nicht vorhanden (—) -->
                <!-- Spalte 5: Impulse -->
                <td style="color:#00ff99;">{{ msg.impulse_gesamt }}</td>
                <!-- Spalte 6: Verbrauch Gesamt -->
                <td style="color:#00ff99; font-weight:bold;">{{ "%.1f"|format(msg.liter_gesamt) }} L</td>
                <!-- Spalte 7: Verbrauch Session -->
                <td style="color:#aaa;">{{ "%.1f"|format(msg.liter_session) }} L</td>
                <!-- Spalte 8: Distanz (nicht vorhanden) -->
                <td style="color:#555;">&#8212;</td>
                <!-- Spalte 9: Batterie -->
                {% if msg.batterie_v < 12.0 %}
                    <td class="value-warn">{{ "%.2f"|format(msg.batterie_v) }} V</td>
                {% else %}
                    <td class="value-ok">{{ "%.2f"|format(msg.batterie_v) }} V</td>
                {% endif %}
            {% else %}
                <!-- HC-SR04: Distanz + Batterie befüllen; Wasserverbrauch-Felder sind nicht vorhanden (—) -->
                <!-- Spalte 5: Impulse (nicht vorhanden) -->
                <td style="color:#555;">&#8212;</td>
                <!-- Spalte 6: Verbrauch Gesamt (nicht vorhanden) -->
                <td style="color:#555;">&#8212;</td>
                <!-- Spalte 7: Verbrauch Session (nicht vorhanden) -->
                <td style="color:#555;">&#8212;</td>
                <!-- Spalte 8: Distanz -->
                {% if msg.distanz_cm == -1 %}
                    <td style="color:#888;">kein Objekt</td>
                {% else %}
                    <td style="color:#00d4ff;">{{ "%.1f"|format(msg.distanz_cm) }} cm</td>
                {% endif %}
                <!-- Spalte 9: Batterie -->
                {% if msg.batterie_v < 12.0 %}
                    <td class="value-warn">{{ "%.2f"|format(msg.batterie_v) }} V</td>
                {% else %}
                    <td class="value-ok">{{ "%.2f"|format(msg.batterie_v) }} V</td>
                {% endif %}
            {% endif %}
        </tr>
        {% endfor %}
    </table>

    <p class="footer">
        Server läuft auf Port 5000 &nbsp;|&nbsp;
        Geräte gesamt: {{ devices_lj18a3|length + devices_schall|length }}
    </p>
</body>
</html>
"""

# ============================================================
#  API Endpunkt - Sensordaten empfangen
# ============================================================
@app.route('/api/data', methods=['POST'])
def empfange_daten():
    global messages

    try:
        daten = request.get_json(force=True)
        if not daten:
            return jsonify({"fehler": "Kein JSON empfangen"}), 400

        ip       = daten.get('ip', request.remote_addr)
        now_str  = datetime.now().strftime('%H:%M:%S')
        sensor_typ = daten.get('sensor_typ', 'HC-SR04')

        with data_lock:
            if sensor_typ == 'LJ18A3':
                # ---- Wasser-Monitor Daten ----
                devices_lj18a3[ip] = {
                    'uptime':         daten.get('uptime', '--'),
                    'uptime_ms':      daten.get('uptime_ms', 0),
                    'liter_gesamt':   float(daten.get('liter_gesamt', 0)),
                    'liter_session':  float(daten.get('liter_session', 0)),
                    'impulse_gesamt': int(daten.get('impulse_gesamt', 0)),
                    'batterie_v':     float(daten.get('batterie_v', 0)),
                    'firmware':       daten.get('firmware', '?'),
                    # display_an: True = Display AN, False = Display AUS
                    # Standardwert True falls das Feld im JSON fehlt (Abwaertskompatibilitaet)
                    'display_an':     bool(daten.get('display_an', True)),
                    'last_seen':      now_str
                }
                details = (f"Liter: {daten.get('liter_gesamt', 0):.1f} L | "
                           f"Session: {daten.get('liter_session', 0):.1f} L | "
                           f"Batt: {daten.get('batterie_v', 0):.2f}V | "
                           f"FW: v{daten.get('firmware', '?')}")

            else:
                # ---- Ultraschall-Monitor Daten (HC-SR04) ----
                # Rueckwaertskompatibel: distanz_cm kann fehlen -> -1
                devices_schall[ip] = {
                    'uptime':     daten.get('uptime', '--'),
                    'uptime_ms':  daten.get('uptime_ms', 0),
                    'distanz_cm': float(daten.get('distanz_cm', -1)),
                    'batterie_v': float(daten.get('batterie_v', 0)),
                    'firmware':   daten.get('firmware', '?'),
                    # display_an: True = Display AN, False = Display AUS
                    # Standardwert True falls das Feld im JSON fehlt (Abwaertskompatibilitaet)
                    'display_an': bool(daten.get('display_an', True)),
                    'last_seen':  now_str
                }
                details = (f"Distanz: {daten.get('distanz_cm', -1)} cm | "
                           f"Batt: {daten.get('batterie_v', 0):.2f}V | "
                           f"FW: v{daten.get('firmware', '?')}")

            # Nachrichten-Log
            if sensor_typ == 'LJ18A3':
                # LJ18A3: Wasserverbrauch-Felder befüllen; Distanz nicht vorhanden → -1
                messages.append({
                    'zeit':           now_str,
                    'ip':             ip,
                    'typ':            sensor_typ,
                    'details':        details,
                    'impulse_gesamt': int(daten.get('impulse_gesamt', 0)),
                    'liter_gesamt':   float(daten.get('liter_gesamt', 0)),
                    'liter_session':  float(daten.get('liter_session', 0)),
                    'distanz_cm':     -1,                                    # LJ18A3 hat keine Distanzmessung
                    'batterie_v':     float(daten.get('batterie_v', 0)),     # Batteriespannung in Volt
                })
            else:
                # HC-SR04: Distanz + Batterie befüllen; Wasserverbrauch nicht vorhanden → 0
                messages.append({
                    'zeit':           now_str,
                    'ip':             ip,
                    'typ':            sensor_typ,
                    'details':        details,
                    'impulse_gesamt': 0,                                     # HC-SR04 hat keinen Impulszähler
                    'liter_gesamt':   0.0,                                   # HC-SR04 misst keinen Wasserverbrauch
                    'liter_session':  0.0,                                   # HC-SR04 misst keinen Wasserverbrauch
                    'distanz_cm':     float(daten.get('distanz_cm', -1)),    # Distanz in cm (-1 = kein Objekt)
                    'batterie_v':     float(daten.get('batterie_v', 0)),     # Batteriespannung in Volt
                })
            if len(messages) > 100:
                messages = messages[-100:]

        print(f"[{now_str}] {sensor_typ} von {ip}: {details}")
        return jsonify({"status": "ok"}), 200

    except Exception as e:
        print(f"Fehler beim Verarbeiten: {e}")
        return jsonify({"fehler": str(e)}), 500


# ============================================================
#  OTA Endpunkte - SCHALL (HC-SR04)
# ============================================================
@app.route('/firmware/schall/version', methods=['GET'])
def fw_schall_version():
    """Gibt die aktuelle Schall-Firmware Version zurück."""
    ver = lese_version(FW_SCHALL_VER)
    return jsonify({"version": ver, "typ": "HC-SR04"}), 200


@app.route('/firmware/schall/download', methods=['GET'])
def fw_schall_download():
    """Liefert die Schall-Firmware .bin Datei."""
    if not os.path.exists(FW_SCHALL_BIN):
        return "Keine Schall-Firmware vorhanden", 404
    return send_file(FW_SCHALL_BIN,
                     mimetype='application/octet-stream',
                     as_attachment=True,
                     download_name='firmware_schall.bin')


# ============================================================
#  OTA Endpunkte - LJ18A3 (Wasser-Monitor)
# ============================================================
@app.route('/firmware/lj18a3/version', methods=['GET'])
def fw_lj18a3_version():
    """Gibt die aktuelle LJ18A3-Firmware Version zurück."""
    ver = lese_version(FW_LJ18A3_VER)
    return jsonify({"version": ver, "typ": "LJ18A3"}), 200


@app.route('/firmware/lj18a3/download', methods=['GET'])
def fw_lj18a3_download():
    """Liefert die LJ18A3-Firmware .bin Datei."""
    if not os.path.exists(FW_LJ18A3_BIN):
        return "Keine LJ18A3-Firmware vorhanden", 404
    return send_file(FW_LJ18A3_BIN,
                     mimetype='application/octet-stream',
                     as_attachment=True,
                     download_name='firmware_lj18a3.bin')


# ============================================================
#  Webseite
# ============================================================
@app.route('/')
def webseite():
    with data_lock:
        return render_template_string(
            HTML_TEMPLATE,
            devices_lj18a3 = dict(devices_lj18a3),
            devices_schall = dict(devices_schall),
            messages       = list(messages),
            now            = datetime.now().strftime('%d.%m.%Y %H:%M:%S'),
            fw_lj18a3_ver  = lese_version(FW_LJ18A3_VER),
            fw_schall_ver  = lese_version(FW_SCHALL_VER),
            fw_lj18a3_ok   = os.path.exists(FW_LJ18A3_BIN),
            fw_schall_ok   = os.path.exists(FW_SCHALL_BIN),
        )


# ============================================================
#  Start
# ============================================================
if __name__ == '__main__':
    print("=" * 55)
    print("  ESP32 Monitor Server")
    print("  Port: 5000")
    print("  Unterstützt: HC-SR04 + LJ18A3")
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
    app.run(host='0.0.0.0', port=5000, debug=False)
