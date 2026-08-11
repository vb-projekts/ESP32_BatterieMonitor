// ================================================================
//  ESP32 Wasser-Monitor
//  AZ-Delivery Mini D1 ESP32 (WROOM-32)
//
//  Komponenten:
//    - 1.30" IIC OLED Display V2.1 (SH1106)
//    - LJ18A3-8-Z/BX 5V 6-36V DC (NPN NO) Induktiver Näherungssensor
//    - Batteriespannungsmessung via Spannungsteiler
//    - Lokaler Webserver (Port 80) mit Display Ein/Aus Button
//    - HTTP POST an Raspberry Pi alle 10 Sekunden
//
//  Pin-Belegung:
//    GPIO21  -> OLED SDA
//    GPIO22  -> OLED SCK
//    GPIO27  -> LJ18A3 Signal (NPN NO, interner Pull-up)
//    GPIO34  -> Spannungsteiler Batterie (ADC1)
//    3V3     -> OLED VDD
//    5V/VIN  -> LJ18A3 Braun (VCC)
//    GND     -> OLED GND, LJ18A3 Blau (GND), Spannungsteiler GND
//
//  Anschluss LJ18A3:
//    Braun  -> 5V (VIN)
//    Blau   -> GND
//    Schwarz-> GPIO27 (interner Pull-up, FALLING Interrupt)
//
//  Libraries: U8g2 (Library Manager), alle anderen im ESP32 Core
//  Board: ESP32 Dev Module (NICHT D1_MINI32!)
//  Partition Scheme: Default 4MB with spiffs  (fuer OTA!)
//
//  Changelog:
//    v1.0 - Grundversion: Impulszaehler, Webserver
//    v1.1 - HTTP POST an Raspberry Pi
//    v1.2 - Batteriespannungsmessung
//    v1.3 - Display Ein/Aus Button auf Webseite
//    v1.4 - Kalibrierungsfaktor per Webseite einstellbar
//    v1.5 - OTA Update-Funktion via Raspberry Pi (HTTPUpdate)
// ================================================================

#include <Arduino.h>
#include <U8g2lib.h>
#include <Wire.h>
#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <HTTPUpdate.h>     // im ESP32 Core enthalten

// ================================================================
//  KONFIGURATION - HIER ANPASSEN
// ================================================================
const char* ssid         = "DeinNetzwerkName";
const char* password     = "DeinPasswort";

// URLs zum Raspberry Pi
const char* serverUrl    = "http://192.168.178.46:5000/api/data";
const char* VERSION_URL  = "http://192.168.178.46:5000/firmware/lj18a3/version";
const char* FIRMWARE_URL = "http://192.168.178.46:5000/firmware/lj18a3/download";

// Sendeintervall in Millisekunden (10 Sekunden)
const unsigned long SEND_INTERVAL = 10000;

// ================================================================
//  FIRMWARE VERSION
// ================================================================
#define FIRMWARE_VERSION "1.5"
#define FIRMWARE_TYP     "LJ18A3"

// ================================================================
//  DISPLAY (SH1106 128x64, I2C)
// ================================================================
#define I2C_SDA 21
#define I2C_SCL 22
U8G2_SH1106_128X64_NONAME_F_HW_I2C u8g2(U8G2_R0, U8X8_PIN_NONE);

// ================================================================
//  LJ18A3 SENSOR PIN
// ================================================================
#define LJ18A3_PIN 27   // NPN NO: Ruhezustand HIGH, Metall erkannt = LOW

// ================================================================
//  BATTERIE ADC
// ================================================================
#define BATT_PIN  34
#define R1        100000.0   // 100 kOhm (Reichelt: MPR 100K)
#define R2        27000.0    // 27 kOhm  (Reichelt: METALL 27,0K)
#define ADC_REF   3.3
#define ADC_MAX   4095.0

// Kalibrierungsfaktor als Variable (aenderbar per Webseite!)
// Berechnung: kaliFaktor = Multimeter_Wert / Angezeigter_Wert
float kaliFaktor = 1.05;

// ================================================================
//  LJ18A3 IMPULSZAEHLER
// ================================================================
#define DEBOUNCE_MS      50
#define LITER_PRO_IMPULS 1.0   // 1 Impuls = 1 Liter (Diehl Altair Ti)

volatile unsigned long impulseGesamt  = 0;
volatile unsigned long impulseSession = 0;
volatile unsigned long lastImpulsMs   = 0;

// ================================================================
//  WEBSERVER
// ================================================================
WebServer server(80);

// ================================================================
//  GLOBALE VARIABLEN
// ================================================================
float battSpannung = 0.0;
bool  displayAn    = true;

unsigned long letzteMessung  = 0;
unsigned long letzteAnzeige  = 0;
unsigned long letzterSend    = 0;

// Statusmeldungen
String kaliStatus      = "";
unsigned long kaliStatusZeit = 0;
String updateStatus    = "";

// ================================================================
//  ISR - Interrupt Service Routine fuer LJ18A3
//  NPN NO: Ruhezustand HIGH (Pull-up), Metall erkannt = LOW
//  -> FALLING Flanke = 1 Impuls = 1 Liter
// ================================================================
void IRAM_ATTR onSensorPulse() {
  unsigned long now = millis();
  if ((now - lastImpulsMs) > DEBOUNCE_MS) {
    impulseGesamt++;
    impulseSession++;
    lastImpulsMs = now;
  }
}

// ================================================================
//  HILFSFUNKTIONEN
// ================================================================
float messeBatterie() {
  long summe = 0;
  for (int i = 0; i < 16; i++) {
    summe += analogRead(BATT_PIN);
    delay(5);
  }
  float vPin = (summe / 16.0 / ADC_MAX) * ADC_REF;
  return vPin * ((R1 + R2) / R2) * kaliFaktor;
}

float getLiterGesamt()  { return impulseGesamt  * LITER_PRO_IMPULS; }
float getLiterSession() { return impulseSession * LITER_PRO_IMPULS; }

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
  u8g2.setPowerSave(0);
  server.sendHeader("Location", "/");
  server.send(302, "text/plain", "");
}

void handleDisplayOff() {
  displayAn = false;
  u8g2.setPowerSave(1);
  server.sendHeader("Location", "/");
  server.send(302, "text/plain", "");
}

// ================================================================
//  KALIBRIERUNG HANDLER (v1.4)
// ================================================================
void handleKalibrierung() {
  if (server.hasArg("multimeter")) {
    float multimeterWert = server.arg("multimeter").toFloat();

    if (multimeterWert < 8.0 || multimeterWert > 16.0) {
      kaliStatus = "FEHLER: Wert muss zwischen 8.0V und 16.0V liegen!";
    } else if (battSpannung < 1.0) {
      kaliStatus = "FEHLER: Kein gueltiger Messwert vom ADC!";
    } else {
      float rohwert     = battSpannung / kaliFaktor;
      float neuerFaktor = multimeterWert / rohwert;

      if (neuerFaktor < 0.5 || neuerFaktor > 3.0) {
        kaliStatus = "FEHLER: Faktor ausserhalb Bereich (0.5-3.0)!";
      } else {
        kaliFaktor = neuerFaktor;
        kaliStatus = "OK: Faktor gesetzt auf " + String(kaliFaktor, 3);
        Serial.println("Neuer kaliFaktor: " + String(kaliFaktor, 4));
      }
    }
  } else {
    kaliStatus = "FEHLER: Kein Wert empfangen!";
  }
  kaliStatusZeit = millis();
  server.sendHeader("Location", "/");
  server.send(302, "text/plain", "");
}

// ================================================================
//  OTA UPDATE HANDLER (v1.5)
//  Verwendet /firmware/lj18a3/version und /firmware/lj18a3/download
//  -> Getrennter Endpunkt vom Schall-Board!
// ================================================================
void handleOtaUpdate() {
  HTTPClient http;
  http.begin(VERSION_URL);
  int code = http.GET();

  if (code == 200) {
    String body = http.getString();
    if (body.indexOf(FIRMWARE_VERSION) == -1) {
      updateStatus = "Update laeuft...";
      server.send(200, "text/plain", "Update gestartet! ESP32 startet neu.");
      http.end();

      WiFiClient client;
      t_httpUpdate_return ret = httpUpdate.update(client, FIRMWARE_URL);
      switch (ret) {
        case HTTP_UPDATE_OK:
          break;
        case HTTP_UPDATE_FAILED:
          updateStatus = "Update fehlgeschlagen: " +
                         String(httpUpdate.getLastErrorString());
          break;
        case HTTP_UPDATE_NO_UPDATES:
          updateStatus = "Kein Update verfuegbar.";
          break;
      }
    } else {
      updateStatus = "Bereits aktuell (v" + String(FIRMWARE_VERSION) + ")";
      server.send(200, "text/plain", updateStatus);
    }
  } else {
    updateStatus = "Pi-Server nicht erreichbar! (HTTP " + String(code) + ")";
    server.send(503, "text/plain", updateStatus);
  }
  http.end();
}

// ================================================================
//  HTTP POST AN RASPBERRY PI
// ================================================================
void sendeAnServer() {
  if (WiFi.status() != WL_CONNECTED) return;

  HTTPClient http;
  http.begin(serverUrl);
  http.addHeader("Content-Type", "application/json");

  float litGes = getLiterGesamt();
  float litSes = getLiterSession();

  String json = "{";
  json += "\"uptime\":\"" + uptimeString() + "\",";
  json += "\"uptime_ms\":"  + String(millis()) + ",";
  json += "\"sensor_typ\":\"LJ18A3\",";
  json += "\"impulse_gesamt\":" + String(impulseGesamt) + ",";
  json += "\"liter_gesamt\":"   + String(litGes, 1) + ",";
  json += "\"liter_session\":"  + String(litSes, 1) + ",";
  json += "\"batterie_v\":"     + String(battSpannung, 2) + ",";
  json += "\"display_an\":"     + String(displayAn ? "true" : "false") + ",";
  json += "\"kali_faktor\":"    + String(kaliFaktor, 4) + ",";
  json += "\"firmware\":\"" + String(FIRMWARE_VERSION) + "\",";
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
  String uptimeStr = uptimeString();

  String litGesStr = String(getLiterGesamt(), 1) + " L";
  String litSesStr = String(getLiterSession(), 1) + " L";
  String impStr    = String(impulseGesamt);

  // Kali-Status nur 5 Sekunden anzeigen
  String aktuellerKaliStatus = "";
  if (kaliStatus != "" && (millis() - kaliStatusZeit) < 5000) {
    aktuellerKaliStatus = kaliStatus;
  }

  String html = R"rawhtml(
<!DOCTYPE html>
<html lang="de">
<head>
  <meta charset="UTF-8">
  <meta http-equiv="refresh" content="2">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>ESP32 Wasser-Monitor</title>
  <style>
    body { font-family:'Segoe UI',Arial,sans-serif; background:#1a1a2e;
           color:#eee; display:flex; flex-direction:column; align-items:center;
           justify-content:center; min-height:100vh; margin:0; padding:20px; }
    h1   { color:#00d4ff; margin-bottom:6px; font-size:1.8em; }
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
    .wasser   .card-value { color:#00d4ff; }
    .session  .card-value { color:#00ff99; }
    .batterie .card-value { color:#a8e063; }
    .uptime   .card-value { color:#00d4aa; }
    .dot { display:inline-block; width:10px; height:10px; background:#00ff88;
           border-radius:50%; margin-right:6px; animation:blink 1s infinite; }
    @keyframes blink { 0%,100%{opacity:1} 50%{opacity:.2} }
    .btn { display:inline-block; margin-top:14px; padding:10px 24px;
           border-radius:10px; text-decoration:none; font-weight:bold;
           font-size:.95em; transition:opacity .2s; cursor:pointer; }
    .btn:hover { opacity:.75; }
    .btn-off { background:#ff6b6b22; color:#ff6b6b; border:2px solid #ff6b6b; }
    .btn-on  { background:#00d4aa22; color:#00d4aa; border:2px solid #00d4aa; }
    .status-an  { color:#00ff88; }
    .status-aus { color:#ff6b6b; }
    .kali-box { background:#16213e; border-radius:16px; padding:24px 32px;
                width:100%; max-width:500px; margin-bottom:16px;
                box-shadow:0 4px 24px rgba(0,0,0,.4); border:1px solid #0f3460; }
    .kali-box h3 { color:#e8b86d; margin-bottom:4px; font-size:1.0em;
                   text-transform:uppercase; letter-spacing:2px; }
    .kali-info { font-size:.85em; color:#888; margin-bottom:16px; }
    .kali-row { display:flex; align-items:center; gap:10px; flex-wrap:wrap;
                justify-content:center; }
    .kali-row label { color:#aaa; font-size:.9em; }
    .kali-row input[type=number] { background:#0f3460; color:#eee;
                                   border:1px solid #00d4aa; border-radius:8px;
                                   padding:8px 12px; font-size:1.1em;
                                   width:110px; text-align:center; }
    .kali-row input[type=number]:focus { outline:none; border-color:#e8b86d; }
    .btn-kali { background:#e8b86d22; color:#e8b86d; border:2px solid #e8b86d;
                border-radius:10px; padding:9px 20px; font-weight:bold;
                font-size:.95em; cursor:pointer; transition:opacity .2s; }
    .btn-kali:hover { opacity:.75; }
    .kali-aktuell { font-size:.85em; color:#888; margin-top:10px; }
    .kali-status-ok  { color:#00ff88; font-size:.9em; margin-top:8px; font-weight:bold; }
    .kali-status-err { color:#ff6b6b; font-size:.9em; margin-top:8px; font-weight:bold; }
    .footer { margin-top:20px; font-size:.75em; color:#555; }
  </style>
</head>
<body>
  <h1>&#128167; ESP32 Wasser-Monitor v)rawhtml";
  html += FIRMWARE_VERSION;
  html += R"rawhtml(</h1>
  <p class="subtitle"><span class="dot"></span>Live &ndash; aktualisiert alle 2s</p>

  <div class="cards">

    <!-- Wasserverbrauch Gesamt -->
    <div class="card wasser">
      <div class="card-title">&#128167; Verbrauch Gesamt</div>
      <div class="card-value">)rawhtml";
  html += litGesStr;
  html += R"rawhtml(</div>
      <div class="card-sub">)rawhtml";
  html += impStr + " Impulse";
  html += R"rawhtml(</div>
    </div>

    <!-- Wasserverbrauch Session -->
    <div class="card session">
      <div class="card-title">&#9203; Diese Session</div>
      <div class="card-value">)rawhtml";
  html += litSesStr;
  html += R"rawhtml(</div>
      <div class="card-sub">seit Neustart</div>
    </div>

    <!-- Uptime -->
    <div class="card uptime">
      <div class="card-title">&#9201; Uptime</div>
      <div class="card-value">)rawhtml";
  html += uptimeStr;
  html += R"rawhtml(</div>
    </div>

    <!-- Batterie -->
    <div class="card batterie">
      <div class="card-title">&#128267; Batterie</div>
      <div class="card-value">)rawhtml";
  html += String(battSpannung, 2) + " V";
  html += R"rawhtml(</div>
      <div class="card-sub">)rawhtml";
  html += ladestandText(battSpannung);
  html += R"rawhtml(</div>
    </div>

    <!-- Display Ein/Aus -->
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

    <!-- Firmware Update -->
    <div class="card">
      <div class="card-title">&#128257; Firmware</div>
      <div class="card-value" style="font-size:1.2em; color:#a78bfa">v)rawhtml";
  html += FIRMWARE_VERSION;
  html += R"rawhtml(</div>)rawhtml";

  if (updateStatus != "") {
    html += "<div class=\"card-sub\" style=\"color:#a78bfa\">" + updateStatus + "</div>";
  }

  html += R"rawhtml(
      <a href="/ota-update" class="btn" style="background:#a78bfa22;
        color:#a78bfa; border:2px solid #a78bfa;">
        &#128257; Update pruefen
      </a>
    </div>

  </div><!-- /cards -->

  <!-- ====== Kalibrierungs-Box (v1.4) ====== -->
  <div class="kali-box">
    <h3>&#9881; Batterie Kalibrierung</h3>
    <p class="kali-info">
      Multimeter-Wert eingeben &rarr; Kalibrierungsfaktor wird automatisch berechnet.
      Kein Neu-Flashen noetig!
    </p>
    <form action="/kalibrierung" method="GET">
      <div class="kali-row">
        <label>Multimeter zeigt:</label>
        <input type="number" name="multimeter" step="0.01"
               min="8.0" max="16.0" placeholder="z.B. 12.53" required>
        <span style="color:#aaa">V</span>
        <button type="submit" class="btn-kali">&#10003; Kalibrieren</button>
      </div>
    </form>
    <p class="kali-aktuell">
      Aktueller Faktor: <strong style="color:#e8b86d">)rawhtml";
  html += String(kaliFaktor, 4);
  html += R"rawhtml(</strong>
      &nbsp;&bull;&nbsp; ESP32 misst gerade: <strong style="color:#a8e063">)rawhtml";
  html += String(battSpannung, 2) + " V";
  html += R"rawhtml(</strong>
    </p>)rawhtml";

  if (aktuellerKaliStatus != "") {
    if (aktuellerKaliStatus.startsWith("OK")) {
      html += "<p class=\"kali-status-ok\">&#10003; " + aktuellerKaliStatus + "</p>";
    } else {
      html += "<p class=\"kali-status-err\">&#10005; " + aktuellerKaliStatus + "</p>";
    }
  }

  html += R"rawhtml(
  </div><!-- /kali-box -->

  <div class="footer">)rawhtml";
  html += WiFi.localIP().toString();
  html += R"rawhtml( &bull; LJ18A3 Induktiv &bull; v)rawhtml";
  html += FIRMWARE_VERSION;
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

  Wire.begin(I2C_SDA, I2C_SCL);
  u8g2.begin();

  // LJ18A3: NPN NO -> interner Pull-up, FALLING Interrupt
  pinMode(LJ18A3_PIN, INPUT_PULLUP);
  attachInterrupt(digitalPinToInterrupt(LJ18A3_PIN), onSensorPulse, FALLING);
  Serial.println("LJ18A3 Interrupt aktiv auf GPIO27");

  analogSetAttenuation(ADC_11db);

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

  u8g2.clearBuffer();
  u8g2.setFont(u8g2_font_ncenB08_tr);
  u8g2.drawStr(0, 14, "WiFi OK!");
  u8g2.drawStr(0, 30, WiFi.localIP().toString().c_str());
  u8g2.drawStr(0, 46, "Pi-Server:");
  u8g2.setFont(u8g2_font_6x10_tr);
  u8g2.drawStr(0, 60, serverUrl);
  u8g2.sendBuffer();
  delay(4000);

  // Alle Routen registrieren
  server.on("/",             handleRoot);
  server.on("/display/on",   handleDisplayOn);
  server.on("/display/off",  handleDisplayOff);
  server.on("/kalibrierung", handleKalibrierung);   // v1.4
  server.on("/ota-update",   handleOtaUpdate);      // v1.5
  server.begin();

  Serial.println("Webserver v" + String(FIRMWARE_VERSION) + " gestartet.");
  Serial.println("OTA verfuegbar: http://" + WiFi.localIP().toString() + "/ota-update");
  Serial.println("KaliFaktor: " + String(kaliFaktor, 4));
}

// ================================================================
//  LOOP
// ================================================================
void loop() {
  server.handleClient();

  unsigned long jetzt = millis();

  // Batterie alle 500ms messen
  if (jetzt - letzteMessung >= 500) {
    letzteMessung = jetzt;
    battSpannung  = messeBatterie();
  }

  // Display alle 500ms aktualisieren
  if (jetzt - letzteAnzeige >= 500 && displayAn) {
    letzteAnzeige = jetzt;

    String uptimeStr = uptimeString();
    String ipStr     = WiFi.localIP().toString();
    char bufGes[20], bufSes[20];
    snprintf(bufGes, sizeof(bufGes), "Ges: %.1f L", getLiterGesamt());
    snprintf(bufSes, sizeof(bufSes), "Ses: %.1f L", getLiterSession());

    u8g2.clearBuffer();
    u8g2.setFont(u8g2_font_ncenB08_tr);
    u8g2.drawStr(20, 12, "Wasser-Monitor");
    u8g2.drawHLine(0, 15, 128);

    // Wasserverbrauch
    u8g2.setFont(u8g2_font_6x10_tr);
    u8g2.drawStr(0, 27, bufGes);
    u8g2.drawStr(0, 38, bufSes);

    // Batterie
    char bufBatt[20];
    snprintf(bufBatt, sizeof(bufBatt), "Batt: %.2fV", battSpannung);
    u8g2.drawStr(0, 49, bufBatt);

    u8g2.drawHLine(0, 52, 128);
    u8g2.setFont(u8g2_font_ncenB08_tr);
    u8g2.drawStr(0, 63, ipStr.c_str());
    u8g2.sendBuffer();
  }

  // HTTP POST alle 10 Sekunden
  if (jetzt - letzterSend >= SEND_INTERVAL) {
    letzterSend = jetzt;
    sendeAnServer();
  }
}
