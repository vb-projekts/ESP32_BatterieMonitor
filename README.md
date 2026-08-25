# 🔋💧 ESP32 Multi-Sensor Monitor (Batterie + Wasserverbrauch)

Ein Multi-Board-Monitoring-System auf Basis von **AZ-Delivery Mini D1 ESP32 (WROOM-32)**-Boards,
das von **einem gemeinsamen Raspberry Pi Server** (Flask, Python) empfangen, gespeichert und
als Web-Dashboard dargestellt wird.

Aktuell werden zwei Sensor-Typen unterstützt:

| Board | Sensor | Zweck | Firmware |
|---|---|---|---|
| **Ultraschall-/Batterie-Monitor** | HC-SR04 + Spannungsteiler | Distanzmessung + 12V Autobatterie-Überwachung | `Uptime_Schall.ino` |
| **Wasser-Monitor** | LJ18A3 Induktiver Näherungssensor | Wasserverbrauch (Impulszähler am Wasserzähler) | `../WaterMeasurer/Code/Uptime_LJ18A3.ino` (v1.7) |

Beide Boards senden ihre Daten per HTTP POST an **denselben** Raspberry Pi Server (`server.py`),
der sie unterscheidet, getrennt verarbeitet und auf verschiedenen Webseiten anzeigt.

---

## 📋 Features

### Allgemein / Server
- 🌐 **3 Webseiten**: Übersicht (`/`), Wasserverbrauch (`/wasser`), Admin (`/admin`)
- ⚡ **Live-Updates per JavaScript** (`fetch()`-Polling) – kein `<meta refresh>`, kein Neuladen der Seite, kein Scroll-Reset
- 🟢 **Online/Offline-Erkennung** pro Board (Status-Badge, blinkender Punkt, Zusammenfassungs-Karten)
- 🔢 **Versionsanzeige** in der Navigationsleiste (`v{{ server_version }}`), damit man beim Deployment den Überblick behält
- 🗂️ Saubere Projektstruktur: `templates/` (Jinja2, mit `base.html`-Vererbung), `static/` (CSS/JS getrennt), `wasserdb/` (SQLite-Datenschicht)

### Ultraschall-/Batterie-Monitor
- ⏱ **Uptime-Anzeige** auf 1.30" OLED Display (HH:MM:SS)
- 📡 **Distanzmessung** mit HC-SR04 Ultraschallsensor
- 🔋 **Batteriespannungsmessung** (12V Autobatterie via Spannungsteiler) inkl. Kalibrierungsfaktor per Webseite
- 💡 **Display Ein/Aus** direkt über die Webseite steuerbar
- 🔄 **OTA-Firmware-Update** über den Raspberry Pi

### Wasser-Monitor (LJ18A3)
- 💧 **Impulszähler** (1 Impuls = 1 Liter), Zählerstand seit letztem ESP32-Neustart
- 🎯 **Kalibrierbarer Gesamtverbrauch** – übersteht ESP32-Neustarts (siehe Admin-Seite), da dein physischer Wasserzähler ja nicht bei 0 anfängt
- 🌀 **Rotierende "Wasseruhr"**: ein SVG-Rad dreht sich weich schneller/langsamer, exakt passend zum aktuellen Durchfluss (exponentiell geglättet, kein Springen)
- 📊 **Verlaufs-Diagramm** (Chart.js) mit Umschaltung Stunde / Tag / Woche (Mo–So) / Monat
- 🖱️ **Klick-Auswahl**: auf eine Geräte-Karte klicken markiert sie (👁️-Symbol) und zeigt ihren Verlauf im Diagramm – nützlich sobald mehrere Wasser-Sensoren angeschlossen sind
- 🗄️ **SQLite-Datenhaltung** (`wasserdb`-Paket): Rohdaten 14 Tage, danach automatisch zu Stunden-/Tages-/Wochen-/Monats­werten verdichtet (Rollup-Hintergrundjob alle 5 Minuten)
- 🔐 **Admin-Seite** (`/admin`, passwortgeschützt): Gesamtverbrauch-Zähler pro Gerät kalibrieren

---

## 🔧 Hardware

| Komponente | Modell | Funktion |
|---|---|---|
| Mikrocontroller (beide Boards) | AZ-Delivery Mini D1 ESP32 (WROOM-32) | Hauptcontroller |
| Display (beide Boards) | 1.30" IIC OLED V2.1 (SH1106, 128x64) | Anzeige + IP |
| Ultraschallsensor | HC-SR04 / HC-SR04+ | Distanzmessung |
| Wassersensor | LJ18A3-8-Z/BX (induktiv, NPN NO) | Impulszählung am Wasserzähler |
| Server | Raspberry Pi (DietPi) | Datenempfang + Dashboard + SQLite |
| Stromversorgung (Batterie-Monitor) | 24V/12V → 5V 5A DC-DC Buck Converter | Versorgung vom Auto |
| Batterie | 12V Blei-Säure Autobatterie | Energiequelle |

---

## 📌 Pin-Belegung

### Ultraschall-/Batterie-Monitor (`Uptime_Schall.ino`)
```
GPIO21  →  OLED SDA
GPIO22  →  OLED SCK
GPIO25  →  HC-SR04 TRIG
GPIO27  →  HC-SR04 ECHO
GPIO34  →  Spannungsteiler Batterie (ADC1)
3V3     →  OLED VDD, HC-SR04 VCC (nur HC-SR04+)
GND     →  OLED GND, HC-SR04 GND
```

### Wasser-Monitor (`Uptime_LJ18A3.ino`, siehe `../WaterMeasurer/Code/`)
```
GPIO21  →  OLED SDA
GPIO22  →  OLED SCK
GPIO27  →  LJ18A3 Signal (Schwarz, interner Pull-up, FALLING Interrupt)
GPIO34  →  Spannungsteiler Batterie (ADC1)
3V3     →  OLED VDD
5V/VIN  →  LJ18A3 Braun (VCC)
GND     →  OLED GND, LJ18A3 Blau (GND), Spannungsteiler GND
```

> ⚠️ **Wichtig:** GPIO34 gehört zu ADC1 — nur ADC1 funktioniert wenn WiFi aktiv ist!

---

## 🔌 Anschlussdiagramme

### OLED Display

```
ESP32 Mini D1                    1.30" IIC OLED V2.1
+------------------+             +------------------+
|  3V3  -----------+-------------+-- VDD            |
|  GND  -----------+-------------+-- GND            |
|  GPIO21 (SDA) ---+-------------+-- SDA            |
|  GPIO22 (SCL) ---+-------------+-- SCK            |
+------------------+             +------------------+
```

### HC-SR04 Ultraschallsensor

```
ESP32 Mini D1                    HC-SR04
+------------------+             +------------------+
|  3V3/5V ---------+-------------+-- VCC            |
|  GND  -----------+-------------+-- GND            |
|  GPIO25 (TRIG) --+-------------+-- TRIG           |
|  GPIO27 (ECHO) --+--[Teiler]---+-- ECHO           |
+------------------+             +------------------+

Spannungsteiler (nur bei 5V HC-SR04 Variante):
ECHO (5V) --- 100kOhm --- GPIO27
                              |
                           27kOhm
                              |
                             GND
```

### LJ18A3 Induktiv-Sensor (Wasser-Monitor)

```
LJ18A3 (3 Adern)                 ESP32 Mini D1
+------------------+             +------------------+
|  Braun (VCC) ----+-------------+-- 5V / VIN       |
|  Blau (GND) -----+-------------+-- GND            |
|  Schwarz (Signal)+-------------+-- GPIO27          |
+------------------+             +------------------+
(interner Pull-up, FALLING Interrupt = 1 Impuls = 1 Liter)
```

### Batteriespannungsmessung

```
Batterie (+) 12V
      |
   [R1 100kOhm]  (Reichelt: MPR 100K, 0.1%)
      |
      +----------- GPIO34 (ESP32)
      |
   [R2 27kOhm]   (Reichelt: METALL 27,0K, 1%)
      |
   [Zener 3.3V]  (Reichelt: BZX 55C3V3 VIS)
      |
   [100nF]       (Reichelt: C3Z5U 100NA50)
      |
     GND (= Buck Converter GND = ESP32 GND)
```

---

## 🛒 Einkaufsliste Batteriespannungsmessung (Reichelt)

| Artikel-Nr. | Beschreibung | Wert | Toleranz | Preis |
|---|---|---|---|---|
| `MPR 100K` | Widerstand Metallschicht 100kOhm, 0207, 0.6W | 100 kΩ | 0.1% | 0.26 € |
| `METALL 27,0K` | Widerstand Metallschicht 27kOhm, 0207, 0.6W | 27 kΩ | 1% | 0.07 € |
| `BZX 55C3V3 VIS` | Zenerdiode 3.3V, 0.5W, DO-35 | 3.3V | — | 0.04 € |
| `C3Z5U 100NA50` | Vielschicht-Kerko 100nF, 50V | 100 nF | — | 0.14 € |

**Gesamtpreis: ca. 1.53 EUR** (je 3 Stück — Ersatz inklusive)

---

## 💻 Software

### ESP32 Arduino Code

**Benötigte Libraries (beide Boards):**

| Library | Installation |
|---|---|
| `U8g2` von Oliver Kraus | Arduino Library Manager |
| `WiFi`, `WebServer`, `HTTPClient`, `HTTPUpdate`, `Wire` | Im ESP32 Core enthalten |

**Arduino IDE Einstellungen (beide Boards):**

```
Board:            ESP32 Dev Module  ← NICHT D1_MINI32!
Upload Speed:     115200
CPU Frequency:    240 MHz
Flash Size:       4MB
Partition Scheme: Default 4MB with spiffs   (für OTA-Updates nötig!)
```

**Konfiguration im Code anpassen (beide `.ino`-Dateien):**

```cpp
const char* ssid      = "DeinNetzwerkName";
const char* password  = "DeinPasswort";
const char* serverUrl = "http://<Pi-IP>:5000/api/data";
```

> 🔒 **GitHub-Hinweis:** Bevor du den Code committest, ersetze deine echten WLAN-Zugangsdaten
> wieder durch Platzhalter (oder lagere sie in eine nicht versionierte `secrets.h` aus) — sonst
> landen SSID und Passwort im öffentlichen Repository!

**Firmware Update / Export als `.bin` für OTA:**

Statt normal hochzuladen: **Sketch → Export Compiled Binary**. Die Datei
`<Sketchname>.ino.bin` umbenennen in `firmware.bin` und auf dem Pi ablegen
(siehe Abschnitt "OTA Firmware Update" unten).

---

### Raspberry Pi Server (`server.py`)

**Installation auf DietPi:**

```bash
# 1. Voraussetzungen
sudo apt install python3-venv -y

# 2. Projektordner + Virtual Environment
mkdir -p ~/esp32-monitor
python3 -m venv ~/esp32-monitor/venv
source ~/esp32-monitor/venv/bin/activate

# 3. Flask installieren (sqlite3 ist bereits Teil von Python, kein extra Paket nötig)
pip install flask

# 4. Projektdateien kopieren (server.py, templates/, static/, wasserdb/)
#    z.B. per WinSCP/scp in ~/esp32-monitor/ übertragen
python ~/esp32-monitor/server.py
```

**Ordnerstruktur, die server.py erwartet** (liegt alles im selben Verzeichnis):

```
esp32-monitor/
├── server.py
├── wasserdb/               ← SQLite-Datenschicht (siehe unten)
├── templates/              ← Jinja2-Templates
├── static/
│   ├── css/style.css
│   └── js/
│       ├── common.js
│       ├── app.js
│       ├── wasser.js
│       └── vendor/chart.min.js   ← manuell besorgen, siehe unten
├── data/                   ← wird automatisch angelegt (SQLite-Datenbank)
└── firmware/               ← wird automatisch angelegt (OTA .bin-Dateien)
```

**Chart.js besorgen** (wird für das Verlaufs-Diagramm auf `/wasser` gebraucht):

```bash
cd ~/esp32-monitor/static/js
mkdir -p vendor
cd vendor
wget https://cdn.jsdelivr.net/npm/chart.js -O chart.min.js
```

> ⚠️ Es muss die **UMD-Version** sein (funktioniert mit normalem `<script src="...">`), nicht die
> ES-Module-Version. Der obige jsDelivr-Link liefert automatisch die richtige Variante.

**Optional: SQLite-CLI zum manuellen Reinschauen in die Datenbank:**

```bash
sudo apt install sqlite3
sudo sqlite3 ~/esp32-monitor/data/wasserverbrauch.db "SELECT * FROM messwerte ORDER BY id DESC LIMIT 10;"
```
(Der `sudo` ist nötig, weil der Server als `root` läuft und die Datenbankdatei entsprechend gehört.)

**Autostart mit systemd:**

```bash
sudo nano /etc/systemd/system/esp32-monitor.service
```

```ini
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
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable esp32-monitor
sudo systemctl start esp32-monitor
```

**Nach Änderungen an server.py / Templates / JS neu starten:**

```bash
sudo systemctl restart esp32-monitor
sudo systemctl status esp32-monitor
journalctl -u esp32-monitor -n 50   # Fehlersuche
```

> 💡 Reine Frontend-Änderungen (nur CSS/JS, keine Python-Änderung) benötigen **keinen**
> Server-Neustart — ein Hard-Refresh im Browser (Strg+F5) reicht.

---

## 🔐 Admin-Seite einrichten (wichtig!)

Die Admin-Seite (`/admin`) erlaubt das Kalibrieren des Gesamtverbrauch-Zählers und ist
passwortgeschützt. **Vor dem produktiven Einsatz unbedingt ändern:**

```python
# in server.py
ADMIN_PASSWORT = "aendere-mich"   # <-- durch ein echtes Passwort ersetzen!
```

> 🔒 **GitHub-Hinweis:** Setze dieses Passwort **nicht** fest im Code, bevor du zu GitHub
> pushst — entweder erst nach dem Klonen lokal ändern, oder besser über eine Umgebungsvariable
> (`os.environ.get("ADMIN_PASSWORT", "...")`) und eine nicht versionierte `.env`-Datei laden.

Beim erstmaligen Kalibrieren auf `/admin`: den **tatsächlichen aktuellen Zählerstand** deines
physischen Wasserzählers eintragen, da dieser ja nicht bei 0 beginnt. Ab diesem Wert wird
korrekt weitergezählt — auch über künftige ESP32-Neustarts hinweg.

---

## 🌐 Webseiten & API

| URL | Beschreibung |
|---|---|
| `http://<ESP32-IP>/` | ESP32 lokales Dashboard (jeweiliges Board) |
| `http://<ESP32-IP>/display/on` \| `/display/off` | OLED Display ein-/ausschalten |
| `http://<ESP32-IP>/ota-update` | OTA-Update manuell anstoßen |
| `http://<Pi-IP>:5000/` | Übersicht: alle Boards, Online/Offline, Nachrichten-Log |
| `http://<Pi-IP>:5000/wasser` | Wasserverbrauch: Meter-Karten, Wasserrad, Diagramm |
| `http://<Pi-IP>:5000/admin` | Admin: Gesamtverbrauch kalibrieren (passwortgeschützt) |
| `http://<Pi-IP>:5000/api/data` | API Endpunkt für ESP32-Boards (POST, JSON) |
| `http://<Pi-IP>:5000/api/status` | JSON für die Übersichtsseite |
| `http://<Pi-IP>:5000/api/wasser` | JSON für die Wasserverbrauchsseite (Meter-Karten) |
| `http://<Pi-IP>:5000/api/wasser/verlauf?ip=...&zeitraum=stunde\|tag\|woche\|monat` | Verlaufsdaten fürs Diagramm |
| `http://<Pi-IP>:5000/firmware/<typ>/version` \| `/download` | OTA-Endpunkte (`typ` = `schall` oder `lj18a3`) |

**JSON Format ESP32 → Pi (Ultraschall/Batterie):**

```json
{
  "uptime":     "00:12:34",
  "uptime_ms":  754000,
  "distanz_cm": 42.5,
  "batterie_v": 12.54,
  "display_an": true,
  "ip":         "192.168.178.100"
}
```

**JSON Format ESP32 → Pi (Wasser-Monitor, `sensor_typ: "LJ18A3"`):**

```json
{
  "uptime":         "00:12:34",
  "uptime_ms":      754000,
  "sensor_typ":     "LJ18A3",
  "impulse_gesamt": 261,
  "liter_gesamt":   261.0,
  "batterie_v":     12.54,
  "display_an":     true,
  "firmware":       "1.7",
  "ip":             "192.168.178.143"
}
```

> ℹ️ `liter_gesamt` zählt seit dem letzten ESP32-Neustart ("Seit Neustart" in der UI). Der
> **echte, dauerhafte** Gesamtverbrauch ("Gesamtverbrauch" in der UI) wird serverseitig in
> SQLite geführt und übersteht Neustarts (siehe Abschnitt Datenhaltung).

---

## 🗄️ Datenhaltung (Wasserverbrauch, `wasserdb`-Paket)

SQLite-Datenbank unter `data/wasserverbrauch.db` (wird automatisch angelegt, WAL-Modus aktiv
für nebenläufigen Zugriff). Kein manuelles Setup nötig.

| Tabelle | Inhalt | Aufbewahrung |
|---|---|---|
| `messwerte` | Rohe Zählerstände, ein Eintrag pro empfangenem Messwert | 14 Tage, danach automatisch gelöscht |
| `verbrauch_stunde` / `_tag` / `_woche` / `_monat` | Aggregierte Verbrauchswerte je Zeitraum | dauerhaft |
| `lebenszeit_verbrauch` | Kalibrierbarer, reset-sicherer Gesamtverbrauch pro Gerät | dauerhaft |

Ein Hintergrund-Thread (`wasserdb/rollup.py`) aggregiert alle 5 Minuten neu und räumt alte
Rohdaten auf. Zähler-Resets (ESP32-Neustart) werden dabei automatisch erkannt und korrekt
behandelt (kein Verlust, keine negativen Werte).

---

## 🔋 Ladezustand Autobatterie

| Spannung | Ladezustand |
|---|---|
| ≥ 12.7V | 100% — voll geladen |
| ≥ 12.4V | 75% |
| ≥ 12.2V | 50% |
| ≥ 12.0V | 25% |
| ≥ 11.8V | ⚠️ Schwach |
| < 11.8V | ❌ LEER — Tiefentladung vermeiden! |

---

## 📁 Projektstruktur

```
ESP/
├── BatterieMonitor/
│   └── Code/
│       ├── Uptime_Schall.ino       # Arduino Code Ultraschall-/Batterie-Board
│       ├── server.py               # Flask Server, verarbeitet BEIDE Sensor-Typen (v2.7)
│       ├── wasserdb/                # SQLite-Datenschicht fuer Wasserverbrauch
│       │   ├── __init__.py         # Verbindung + Schema-Init (WAL-Modus)
│       │   ├── schema.py           # CREATE TABLE Statements
│       │   ├── queries.py          # Insert/Lese-Funktionen, Lebenszeit-Zaehler
│       │   └── rollup.py           # Hintergrund-Aggregation + Pruning
│       ├── templates/
│       │   ├── base.html           # Nav-Leiste, gemeinsames Grundgeruest
│       │   ├── index.html          # Uebersichtsseite "/"
│       │   ├── wasser.html         # Wasserverbrauchsseite "/wasser"
│       │   ├── admin.html          # Admin-Kalibrierung "/admin"
│       │   └── admin_login.html    # Admin-Login
│       ├── static/
│       │   ├── css/style.css
│       │   └── js/
│       │       ├── common.js       # Gemeinsame Helfer (alle Seiten)
│       │       ├── app.js          # Uebersichtsseite
│       │       ├── wasser.js       # Wasserverbrauchsseite (Wasserrad, Diagramm, Klick-Auswahl)
│       │       └── vendor/chart.min.js   # manuell besorgen (siehe Setup)
│       ├── data/                   # SQLite-DB, wird automatisch angelegt (NICHT versionieren!)
│       ├── firmware/                # OTA .bin-Dateien, wird automatisch angelegt
│       └── README.md               # diese Datei
├── WaterMeasurer/
│   └── Code/
│       └── Uptime_LJ18A3.ino       # Arduino Code Wasser-Monitor-Board (v1.7)
└── OnlineMeasurer/
    └── Dokumentation.docx          # Vollstaendige Projektdokumentation (11 Kapitel)
```

---

## 📄 Changelog

### `server.py`

| Version | Änderungen |
|---|---|
| v1.0 – v1.3 | Grundversion: Uptime auf OLED, lokaler Webserver, HTTP POST, Batteriespannung, Display-Steuerung |
| v2.0 | Multi-ESP32-Support (mehrere Boards gleichzeitig) |
| v2.2 | Frontend auf `fetch()`-Polling umgestellt (kein `<meta refresh>` mehr), HTML/CSS/JS in `templates/`/`static/` ausgelagert |
| v2.3 | Nav-Grundgerüst mit `base.html`-Vererbung |
| v2.4 | Neue Seite `/wasser` (rotierende Wasseruhr), Durchfluss-Berechnung, Endpunkt `/api/wasser` |
| v2.5 | SQLite-Datenhaltung (`wasserdb`-Paket): Rohdaten 14 Tage, Rollup zu Stunde/Tag/Woche/Monat, Endpunkt `/api/wasser/verlauf` |
| v2.6 | Kalibrierbarer Lebenszeit-Gesamtverbrauch, passwortgeschützte Admin-Seite (`/admin`), redundantes Session-Feld entfernt |
| v2.7 | Durchfluss-Anzeige exponentiell geglättet (kein Springen mehr zwischen 0 und Spitzenwert) |

### `Uptime_LJ18A3.ino` (Wasser-Monitor)

| Version | Änderungen |
|---|---|
| v1.0 – v1.4 | Grundversion, HTTP POST, Batteriespannung, Kalibrierungsfaktor per Webseite |
| v1.5 | OTA Update-Funktion via Raspberry Pi |
| v1.6 | Sendeintervall 10s → 2s (zeitnahere Verbrauchsanzeige) |
| v1.7 | Redundanten `impulseSession`/`liter_session`-Zähler entfernt (war immer identisch zu `liter_gesamt`), lokale Webseite bereinigt |

### `Uptime_Schall.ino` (Ultraschall-/Batterie-Monitor)

| Version | Änderungen |
|---|---|
| v1.0 | Grundversion: Uptime auf OLED, lokaler Webserver |
| v1.1 | HTTP POST alle 10s an Raspberry Pi, Pi Dashboard |
| v1.2 | Batteriespannungsmessung via Spannungsteiler |
| v1.3 | Display Ein/Aus Button auf Webseite, Display-Status im JSON |

---

## ⚠️ Wichtige Hinweise

- **ESP32 GPIO max. 3.3V** — nie 5V direkt anlegen!
- **ADC1 verwenden** (GPIO32-39) — ADC2 ist bei aktivem WiFi gesperrt
- **Strapping-Pins meiden**: GPIO0, GPIO2, GPIO5, GPIO12, GPIO15 nicht belegen
- **Gemeinsame Masse**: Batterie-Minus = Buck Converter GND = ESP32 GND
- **Spannungsteiler** immer VOR dem Buck Converter an der Rohspannung abgreifen
- **ADC kalibrieren**: `kaliFaktor` mit Multimeter abgleichen (ca. 1.05)
- **Firmware-Änderungen an der `.ino`** müssen über die Arduino IDE (USB oder OTA) neu geflasht
  werden — ein reiner `server.py`-Neustart reicht dafür NICHT aus

---

*Projekt erstellt August 2026 · Multi-Sensor-Erweiterung (Wasserverbrauch, SQLite, Admin-Panel) August 2026*
