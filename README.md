# 🔋 ESP32 Batterie-Monitor

Ein mobiler Sensor-Monitor auf Basis eines **AZ-Delivery Mini D1 ESP32 (WROOM-32)**.  
Der ESP32 wird über ein DC-DC Buck-Converter-Modul von einer 12V Autobatterie versorgt und misst kontinuierlich Distanz, Uptime und Batteriespannung. Die Daten werden auf einem OLED-Display angezeigt, über einen lokalen Webserver bereitgestellt und alle 10 Sekunden an einen Raspberry Pi 5 gesendet.

---

## 📋 Features

- ⏱ **Uptime-Anzeige** auf 1.30" OLED Display (HH:MM:SS)
- 📡 **Distanzmessung** mit HC-SR04 Ultraschallsensor
- 🔋 **Batteriespannungsmessung** (12V Autobatterie via Spannungsteiler)
- 🌐 **Lokaler Webserver** (Port 80) mit Auto-Refresh alle 2 Sekunden
- 📤 **HTTP POST** alle 10 Sekunden an Raspberry Pi Server
- 🖥 **Raspberry Pi Dashboard** mit Nachrichtenverlauf und Online/Offline-Status
- 💡 **Display Ein/Aus** direkt über die Webseite steuerbar
- 📶 **WLAN** Verbindung mit IP-Anzeige auf Display

---

## 🔧 Hardware

| Komponente | Modell | Funktion |
|---|---|---|
| Mikrocontroller | AZ-Delivery Mini D1 ESP32 (WROOM-32) | Hauptcontroller |
| Display | 1.30" IIC OLED V2.1 (SH1106, 128x64) | Uptime + IP Anzeige |
| Ultraschallsensor | HC-SR04 / HC-SR04+ | Distanzmessung |
| Server | Raspberry Pi 5 (DietPi) | Datenempfang + Dashboard |
| Stromversorgung | 24V/12V → 5V 5A DC-DC Buck Converter | Versorgung vom Auto |
| Batterie | 12V Blei-Säure Autobatterie | Energiequelle |

---

## 📌 Pin-Belegung ESP32

```
GPIO21  →  OLED SDA
GPIO22  →  OLED SCK
GPIO25  →  HC-SR04 TRIG
GPIO27  →  HC-SR04 ECHO
GPIO34  →  Spannungsteiler Batterie (ADC1)
3V3     →  OLED VDD, HC-SR04 VCC (nur HC-SR04+)
GND     →  OLED GND, HC-SR04 GND
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

### ESP32 Arduino Code (`Code/Uptime_Schall.ino`)

**Benötigte Libraries:**

| Library | Installation |
|---|---|
| `U8g2` von Oliver Kraus | Arduino Library Manager |
| `WiFi`, `WebServer`, `HTTPClient`, `Wire` | Im ESP32 Core enthalten |

**Arduino IDE Einstellungen:**

```
Board:            ESP32 Dev Module  ← NICHT D1_MINI32!
Upload Speed:     115200
CPU Frequency:    240 MHz
Flash Size:       4MB
Partition Scheme: Default 4MB with spiffs
```

**Konfiguration im Code anpassen:**

```cpp
const char* ssid      = "DeinNetzwerkName";
const char* password  = "DeinPasswort";
const char* serverUrl = "http://<Pi-IP>:5000/api/data";
```

---

### Raspberry Pi Server (`Code/server.py`)

**Installation auf DietPi:**

```bash
# 1. Voraussetzungen
sudo apt install python3-venv -y

# 2. Projektordner + Virtual Environment
mkdir -p ~/esp32-monitor
python3 -m venv ~/esp32-monitor/venv
source ~/esp32-monitor/venv/bin/activate

# 3. Flask installieren
pip install flask

# 4. server.py kopieren und starten
cp server.py ~/esp32-monitor/server.py
python ~/esp32-monitor/server.py
```

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

**Nach Änderungen an server.py neu starten:**

```bash
sudo systemctl restart esp32-monitor
sudo systemctl status esp32-monitor
```

---

## 🌐 Webseiten & API

| URL | Beschreibung |
|---|---|
| `http://<ESP32-IP>/` | ESP32 lokales Dashboard (Auto-Refresh 2s) |
| `http://<ESP32-IP>/display/on` | OLED Display einschalten |
| `http://<ESP32-IP>/display/off` | OLED Display ausschalten |
| `http://<Pi-IP>:5000/` | Raspberry Pi Dashboard (Auto-Refresh 5s) |
| `http://<Pi-IP>:5000/api/data` | API Endpunkt (POST, JSON) |

**JSON Format ESP32 → Pi:**

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
├── Code/
│   ├── Uptime_Schall.ino     # Arduino Code ESP32 (v1.3)
│   └── server.py             # Python Flask Server Raspberry Pi (v1.3)
└── OnlineMeasurer/
    └── Dokumentation.docx    # Vollstaendige Projektdokumentation (11 Kapitel)
```

---

## 📄 Changelog

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
- **ADC kalibrieren**: `KALI_FAKTOR` mit Multimeter abgleichen (ca. 1.05)

---

## 📚 Dokumentation

Eine vollständige Projektdokumentation (Word-Dokument) mit allen Schaltplänen,
Lötanleitungen, Einkaufslisten und Code-Erklärungen befindet sich unter:

```
Dokumentation/Dokumentation.docx
```

---

*Projekt erstellt August 2026*
