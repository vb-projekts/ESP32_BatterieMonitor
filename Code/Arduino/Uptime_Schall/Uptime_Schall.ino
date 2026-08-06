// ================================================================
//  ESP32 Batterie-Monitor
//  AZ-Delivery Mini D1 ESP32 (WROOM-32)
//
//  Komponenten:
//    - 1.30" IIC OLED Display V2.1 (SH1106)
//    - HC-SR04 Ultraschallsensor
//    - Batteriespannungsmessung via Spannungsteiler
//    - Lokaler Webserver (Port 80) mit Display Ein/Aus Button
//    - HTTP POST an Raspberry Pi alle 10 Sekunden
//
//  Pin-Belegung:
//    GPIO21 -> OLED SDA
//    GPIO22 -> OLED SCK
//    GPIO25 -> HC-SR04 TRIG
//    GPIO27 -> HC-SR04 ECHO
//    GPIO34 -> Spannungsteiler Batterie (ADC1)
//    3V3    -> OLED VDD, HC-SR04 VCC (nur HC-SR04+)
//    GND    -> OLED GND, HC-SR04 GND
//
//  Libraries: U8g2 (Library Manager), alle anderen im ESP32 Core
//  Board: ESP32 Dev Module (NICHT D1_MINI32!)
//
//  Changelog:
//    v1.0 - Grundversion: Uptime, Distanz, Webserver
//    v1.1 - HTTP POST an Raspberry Pi
//    v1.2 - Batteriespannungsmessung
//    v1.3 - Display Ein/Aus Button auf Webseite
// ================================================================

#include <Arduino.h>
#include <U8g2lib.h>
#include <Wire.h>
#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>

// ================================================================
//  KONFIGURATION - HIER ANPASSEN
// ================================================================
const char* ssid         = "DeinNetzwerkName";
const char* password     = "DeinPasswort";

// IP des Raspberry Pi eintragen!
const char* serverUrl    = "http://192.168.178.46:5000/api/data";

// Sendeintervall in Millisekunden (10 Sekunden)
const unsigned long SEND_INTERVAL = 10000;

// ================================================================
//  DISPLAY (SH1106 128x64, I2C)
// ================================================================
#define I2C_SDA 21
#define I2C_SCL 22
U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);

// ================================================================
//  HC-SR04 PINS
// ================================================================
#define TRIG_PIN 25
#define ECHO_PIN 27

// ================================================================
//  BATTERIE ADC
// ================================================================
#define BATT_PIN    34
#define R1          100000.0   // 100 kOhm (Reichelt: MPR 100K)
#define R2          27000.0    // 27 kOhm  (Reichelt: METALL 27,0K)
#define ADC_REF     3.3
#define ADC_MAX     4095.0
#define KALI_FAKTOR 1.05       // Anpassen nach Kalibrierung mit Multimeter

// ================================================================
//  WEBSERVER
// ================================================================
WebServer server(80);

// ================================================================
//  GLOBALE VARIABLEN
// ================================================================
float distanzCm    = 0.0;
float battSpannung = 0.0;
bool  displayAn    = true;     // Display-Status: true = AN, false = AUS

unsigned long letzteMessung  = 0;
unsigned long letzteAnzeige  = 0;
unsigned long letzterSend    = 0;

bool zeigeStromAufDisplay = false; // Steuert den Wechsel der Display-Ansicht


// ================================================================
//  HILFSFUNKTIONEN
// ================================================================
float messeDistanz() {
  digitalWrite(TRIG_PIN, LOW);
  delayMicroseconds(2);
  digitalWrite(TRIG_PIN, HIGH);
  delayMicroseconds(10);
  digitalWrite(TRIG_PIN, LOW);
  long dauer = pulseIn(ECHO_PIN, HIGH, 30000);
  if (dauer == 0) return -1.0;
  return (dauer * 0.0343) / 2.0;
}

float messeBatterie() {
  long summe = 0;
  for (int i = 0; i < 16; i++) {
    summe += analogRead(BATT_PIN);
    delay(5);
  }
  float vPin = (summe / 16.0 / ADC_MAX) * ADC_REF;
  return vPin * ((R1 + R2) / R2) * KALI_FAKTOR;
}

// Hilfsfunktion zum Auslesen des INA226 Sensors
void leseINA226() {
  ina226.readAndClearFlags();

  espStrom_mA = ina226.getCurrent_mA();
  espLeistung_mW = ina226.getBusPower_mW();
  busSpannung_V = ina226.getBusVoltage_V();
}

String ladestandText(float v) {
  if (v >= 12.7) return "100% - Voll";
  if (v >= 12.4) return "75%";
  if (v >= 12.2) return "50%";
  if (v >= 12.0) return "25%";
  if (v >= 11.8) return "Schwach!";
  return "LEER!";
}

String uptimeString() {
  unsigned long ms  = millis();
  unsigned long sek = ms / 1000;
  unsigned long min = sek / 60;
  unsigned long std = min / 60;
  sek = sek % 60;
  min = min % 60;
  char buf[12];
  snprintf(buf, sizeof(buf), "%02lu:%02lu:%02lu", std, min, sek);
  return String(buf);
}

// ================================================================
//  DISPLAY EIN/AUS HANDLER
// ================================================================
void handleDisplayOn() {
  displayAn = true;
  u8g2.setPowerSave(0);        // Display physisch einschalten
  server.sendHeader("Location", "/");
  server.send(302, "text/plain", "");
}

void handleDisplayOff() {
  displayAn = false;
  u8g2.setPowerSave(1);        // Display physisch ausschalten (spart Strom!)
  server.sendHeader("Location", "/");
  server.send(302, "text/plain", "");
}

// ================================================================
//  HTTP POST AN RASPBERRY PI
// ================================================================
void sendeAnServer() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(serverUrl);
  http.addHeader("Content-Type", "application/json");

  String distStr = (distanzCm < 0 || distanzCm > 400)
                   ? "-1" : String(distanzCm, 1);

  String json = "{";
  json += "\"uptime\":\"" + uptimeString() + "\",";
  json += "\"uptime_ms\":" + String(millis()) + ",";
  json += "\"distanz_cm\":" + distStr + ",";
  json += "\"batterie_v\":" + String(battSpannung, 2) + ",";
  json += "\"display_an\":" + String(displayAn ? "true" : "false") + ",";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\"";
  json += "}";

  int httpCode = http.POST(json);
  if (httpCode == 200) {
    Serial.println("POST OK: " + json);
  } else {
    Serial.println("POST Fehler: " + String(httpCode));
  }
  http.end();
}

// ================================================================
//  LOKALE WEBSEITE (ESP32 Webserver Port 80)
// ================================================================
void handleRoot() {
  String uptimeStr   = uptimeString();
  String distanzText = (distanzCm < 0 || distanzCm > 400)
                       ? "Kein Objekt" : String(distanzCm, 1) + " cm";

  String html = R"rawhtml(
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="2">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ESP32 Dashboard</title>
  <style>
    body { font-family:'Segoe UI',Arial,sans-serif; background:#1a1a2e;
           color:#eee; display:flex; flex-direction:column; align-items:center;
           justify-content:center; min-height:100vh; margin:0; padding:20px; }
    h1   { color:#00d4aa; margin-bottom:6px; font-size:1.8em; }
    .subtitle { color:#aaa; margin-bottom:30px; font-size:.9em; }
    .cards { display:flex; flex-wrap:wrap; gap:12px; justify-content:center;
             margin-bottom:20px; }
    .card { background:#16213e; border-radius:16px; padding:22px 36px;
            min-width:200px; text-align:center;
            box-shadow:0 4px 24px rgba(0,0,0,.4); }
    .card-title { font-size:.8em; text-transform:uppercase; letter-spacing:2px;
                  color:#888; margin-bottom:8px; }
    .card-value { font-size:2.4em; font-weight:bold; }
    .card-sub   { font-size:.9em; color:#aaa; margin-top:6px; }
    .uptime   .card-value { color:#00d4aa; }
    .distanz  .card-value { color:#e8b86d; }
    .batterie .card-value { color:#a8e063; }
    .dot { display:inline-block; width:10px; height:10px; background:#00ff88;
           border-radius:50%; margin-right:6px; animation:blink 1s infinite; }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.2} }
    .btn {
      display:inline-block; margin-top:14px; padding:10px 24px;
      border-radius:10px; text-decoration:none; font-weight:bold;
      font-size:.95em; transition:opacity .2s; cursor:pointer;
    }
    .btn:hover { opacity:.75; }
    .btn-off { background:#ff6b6b22; color:#ff6b6b;
               border:2px solid #ff6b6b; }
    .btn-on  { background:#00d4aa22; color:#00d4aa;
               border:2px solid #00d4aa; }
    .status-an  { color:#00ff88; }
    .status-aus { color:#ff6b6b; }
    .footer { margin-top:20px; font-size:.75em; color:#555; }
  </style>
</head>
<body>
  <h1>&#128268; ESP32 Dashboard</h1>
  <p class="subtitle"><span class="dot"></span>Live &ndash; aktualisiert alle 2s</p>

  <div class="cards">

    <div class="card uptime">
      <div class="card-title">&#9201; Uptime</div>
      <div class="card-value">)rawhtml";
  html += uptimeStr;
  html += R"rawhtml(</div>
    </div>

    <div class="card distanz">
      <div class="card-title">&#128268; Distanz</div>
      <div class="card-value">)rawhtml";
  html += distanzText;
  html += R"rawhtml(</div>
    </div>

    <div class="card batterie">
      <div class="card-title">&#128267; Batterie</div>
      <div class="card-value">)rawhtml";
  html += String(battSpannung, 2) + " V";
  html += R"rawhtml(</div>
      <div class="card-sub">)rawhtml";
  html += ladestandText(battSpannung);
  html += R"rawhtml(</div>
    </div>

    <!-- Display Ein/Aus Karte -->
    <div class="card">
      <div class="card-title">&#128261; Display</div>)rawhtml";

  if (displayAn) {
    html += R"rawhtml(
      <div class="card-value status-an">AN</div>
      <a href="/display/off" class="btn btn-off">Ausschalten</a>)rawhtml";
  } else {
    html += R"rawhtml(
      <div class="card-value status-aus">AUS</div>
      <a href="/display/on" class="btn btn-on">Einschalten</a>)rawhtml";
  }

  html += R"rawhtml(
    </div>

  </div><!-- /cards -->

  <div class="footer">)rawhtml";
  html += WiFi.localIP().toString();
  html += R"rawhtml( &bull; Sendet alle 10s an Raspberry Pi</div>
</body>
</html>)rawhtml";

  server.send(200, "text/html; charset=utf-8", html);
}

// ================================================================
//  SETUP
// ================================================================
void setup() {
  Serial.begin(115200);

  // Display initialisieren
  Wire.begin(I2C_SDA, I2C_SCL);
  u8g2.begin();

  // INA226 Sensor initialisieren und konfigurieren
  if (!ina226.init()) {
    Serial.println("INA226 konnte nicht initialisiert werden!");
  }
  
  // Konfiguration: Durchschnittsmessung aus 16 Werten, 1.1ms Konvertierungszeit
  ina226.setAverage(AVERAGE_16);
  ina226.setConversionTime(CONVERSION_TIME_1100, CONVERSION_TIME_1100);// Kalibrierung: 0.1 Ohm Shunt (Standard bei den meisten Boards) und max. 800mA erwarteter Stromina226.setResistorRange(0.1, 0.8);

  // HC-SR04
  pinMode(TRIG_PIN, OUTPUT);
  pinMode(ECHO_PIN, INPUT);

  // ADC Daempfung fuer maximalen Messbereich
  analogSetAttenuation(ADC_11db);

  // WLAN verbinden
  Serial.print("Verbinde mit WLAN");
  WiFi.begin(ssid, password);

  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB08_tr);
  u8g2.drawStr(0, 20, "Verbinde WLAN...");
  u8g2.sendBuffer();

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }
  Serial.println("\nIP: " + WiFi.localIP().toString());

  // IP kurz auf Display anzeigen
  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB08_tr);
  u8g2.drawStr(0, 14, "WiFi OK!");
  u8g2.drawStr(0, 30, WiFi.localIP().toString().c_str());
  u8g2.drawStr(0, 46, "Pi-Server:");
  u8g2.setFont(u8g2_font_6x10_tr);
  u8g2.drawStr(0, 60, serverUrl);
  u8g2.sendBuffer();
  delay(4000);

  // Webserver Routen registrieren
  server.on("/",            handleRoot);
  server.on("/display/on",  handleDisplayOn);
  server.on("/display/off", handleDisplayOff);
  server.begin();
  Serial.println("Webserver gestartet.");
}

// ================================================================
//  LOOP
// ================================================================
void loop() {
  server.handleClient();

  unsigned long jetzt = millis();

  // Sensoren alle 500ms messen
  if (jetzt - letzteMessung >= 500) {
    letzteMessung = jetzt;
    distanzCm    = messeDistanz();
    battSpannung = messeBatterie();
    leseINA226(); // INA226 Daten alle 500ms abrufen
  }

  // Display alle 500ms aktualisieren - NUR wenn Display AN ist!
  if (jetzt - letzteAnzeige >= 500 && displayAn) {
    letzteAnzeige = jetzt;

    String uptimeStr = uptimeString();
    String ipStr     = WiFi.localIP().toString();

    u8g2.clearBuffer();

    // Uptime Bereich
    u8g2.setFont(u8g2_font_ncenB08_tr);
    u8g2.drawStr(20, 12, "ESP32 Uptime");
    u8g2.drawHLine(0, 15, 128);
    u8g2.drawCircle(10, 30, 7);
    u8g2.drawLine(10, 30, 10, 25);
    u8g2.drawLine(10, 30, 14, 30);
    u8g2.setFont(u8g2_font_logisoso16_tr);
    u8g2.drawStr(22, 38, uptimeStr.c_str());

    // Trennlinie
    u8g2.drawHLine(0, 42, 128);

    // Automatischer Wechsel alle 3 Sekunden (3000ms Taktung ueber millis)
    if ((jetzt / 3000) % 2 == 0) {
      // ANSICHT 1: IP-Adresse und Webserver-Status
      u8g2.setFont(u8g2_font_ncenB08_tr);
      u8g2.drawStr(0, 53, "IP:");
      u8g2.setFont(u8g2_font_6x10_tr);
      u8g2.drawStr(20, 53, ipStr.c_str());
      u8g2.drawStr(0, 63, "Webserver aktiv");
    } else {
      // ANSICHT 2: Live-Energieverbrauch vom INA226
      u8g2.setFont(u8g2_font_ncenB08_tr);
      u8g2.drawStr(0, 53, "Power:");
      u8g2.setFont(u8g2_font_6x10_tr);
      
      // Formatierung: "X mA (Y mW)" zusammensetzen
      String stromAnzeige = String(espStrom_mA, 0) + "mA (" + String(espLeistung_mW, 0) + "mW)";
      u8g2.drawStr(42, 53, stromAnzeige.c_str());
      
      // Untere Statuszeile waehrend der Strommessung
      u8g2.drawStr(0, 63, "INA226 Live-Messung");
    }

    u8g2.sendBuffer();
  }

  // Alle 10 Sekunden Daten an Raspberry Pi senden
  if (jetzt - letzterSend >= SEND_INTERVAL) {
    letzterSend = jetzt;
    sendeAnServer();
  }
}