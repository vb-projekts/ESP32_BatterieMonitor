// ================================================================
//  ESP32 Garage-Monitor & Control (v1.1)
//  Steuert 2 Garagentore (Relais) und überwacht 4 Distanzen (HC-SR04)
//
//  Komponenten:
//    - 4x HC-SR04 Ultraschallsensoren (Tor 1, Tor 2, Auto 1, Auto 2)
//    - 2-Kanal Relais Modul (Potentialfreier Kontakt für Taster)
//    - Lokaler Webserver (Port 80) zur Statusanzeige & Steuerung
//    - HTTP POST an Raspberry Pi alle 1 Sekunden
//
// ================================================================

#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <HTTPUpdate.h>

// ================================================================
//  KONFIGURATION
// ================================================================
const char* ssid         = "GarageAA";
const char* password     = "espConnector#1";

// URLs zum Raspberry Pi
const char* serverUrl    = "http://192.168.178.46:5000/api/data";
const char* VERSION_URL  = "http://192.168.178.46:5000/firmware/garage/version";
const char* FIRMWARE_URL = "http://192.168.178.46:5000/firmware/garage/download";

const unsigned long SEND_INTERVAL = 1000; // Alle 1 Sekunde senden

#define FIRMWARE_VERSION "1.2"

// Pins
#define RELAY1_PIN 23
#define RELAY2_PIN 33

struct US_Sensor {
  int trig;
  int echo;
  float dist;
};

// Set
US_Sensor sTor1  = {18, 35, 0.0};
US_Sensor sAuto1 = {25, 22, 0.0};

// Need to be set
US_Sensor sTor2  = {19, 21, 0.0};
US_Sensor sAuto2 = {32, 26, 0.0};

WebServer server(80);
unsigned long letzterSend = 0;
String updateStatus = "";

// ================================================================
//  HILFSFUNKTIONEN
// ================================================================
float messeDistanz(int trig, int echo) {
  digitalWrite(trig, LOW);
  delayMicroseconds(2);
  digitalWrite(trig, HIGH);
  delayMicroseconds(10);
  digitalWrite(trig, LOW);
  long dauer = pulseIn(echo, HIGH, 30000);
  if (dauer == 0) return -1.0;
  return (dauer * 0.0343) / 2.0;
}

void triggerRelais(int pin) {
  digitalWrite(pin, LOW);  // Relais aus (öffnet NO-COM, simuliert Taster)
  delay(500);              // 500ms halten
  digitalWrite(pin, HIGH); // Relais an (schließt NO-COM wieder)
}

String uptimeString() {
  unsigned long sek = millis() / 1000;
  char buf[12];
  snprintf(buf, sizeof(buf), "%02lu:%02lu:%02lu", (sek/3600), (sek%3600)/60, (sek%60));
  return String(buf);
}

// ================================================================
//  WEB-HANDLER
// ================================================================
void handleRoot() {
  String html = "<!DOCTYPE html><html lang='de'><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1'><meta http-equiv='refresh' content='3'>";
  html += "<title>Garage ESP32</title><style>body{font-family:sans-serif;background:#1a1a2e;color:#eee;text-align:center;padding:20px;}";
  html += ".card{background:#16213e;border-radius:15px;padding:20px;margin:10px;display:inline-block;min-width:150px;}";
  html += ".btn{display:block;width:100%;padding:15px;margin-top:10px;border-radius:10px;border:none;font-weight:bold;cursor:pointer;font-size:1.1em;}";
  html += ".btn-t1{background:#e8b86d;color:#1a1a2e;}.btn-t2{background:#00d4ff;color:#1a1a2e;}</style></head><body>";
  html += "<h1>🚗 Garage Control v" + String(FIRMWARE_VERSION) + "</h1>";
  html += "<p>IP: " + WiFi.localIP().toString() + " | Uptime: " + uptimeString() + "</p>";
  
  html += "<div class='card'><h3>Tor 1</h3><p>" + String(sTor1.dist, 1) + " cm</p><button class='btn btn-t1' onclick=\"location.href='/trigger/1'\">Taster 1</button></div>";
  html += "<div class='card'><h3>Tor 2</h3><p>" + String(sTor2.dist, 1) + " cm</p><button class='btn btn-t2' onclick=\"location.href='/trigger/2'\">Taster 2</button></div><br>";
  html += "<div class='card'><h3>Auto 1</h3><p>" + String(sAuto1.dist, 1) + " cm</p></div>";
  html += "<div class='card'><h3>Auto 2</h3><p>" + String(sAuto2.dist, 1) + " cm</p></div>";
  
  html += "<p style='margin-top:30px;'><a href='/ota-update' style='color:#a78bfa;text-decoration:none;'>Update prüfen</a><br>" + updateStatus + "</p>";
  html += "</body></html>";
  server.send(200, "text/html", html);
}

void handleTrigger1() { triggerRelais(RELAY1_PIN); server.sendHeader("Location", "/"); server.send(302); }
void handleTrigger2() { triggerRelais(RELAY2_PIN); server.sendHeader("Location", "/"); server.send(302); }

void handleOtaUpdate() {
  HTTPClient http;
  http.begin(VERSION_URL);
  if (http.GET() == 200) {
    if (http.getString().indexOf(FIRMWARE_VERSION) == -1) {
      server.send(200, "text/plain", "Update startet...");
      WiFiClient client;
      httpUpdate.update(client, FIRMWARE_URL);
    } else {
      updateStatus = "Bereits aktuell.";
      server.sendHeader("Location", "/"); server.send(302);
    }
  }
  http.end();
}

// ================================================================
//  SERVER POST
// ================================================================
void sendeAnServer() {
  if (WiFi.status() != WL_CONNECTED) return;
  HTTPClient http;
  http.begin(serverUrl);
  http.addHeader("Content-Type", "application/json");

  // JSON manuell bauen (schlank und ohne Library)
  String json = "{";
  json += "\"sensor_typ\":\"Garage\",";
  json += "\"ip\":\"" + WiFi.localIP().toString() + "\",";
  json += "\"uptime\":\"" + uptimeString() + "\",";
  json += "\"uptime_ms\":" + String(millis()) + ",";
  json += "\"tor1_cm\":" + String(sTor1.dist, 1) + ",";
  json += "\"tor2_cm\":" + String(sTor2.dist, 1) + ",";
  json += "\"auto1_cm\":" + String(sAuto1.dist, 1) + ",";
  json += "\"auto2_cm\":" + String(sAuto2.dist, 1) + ",";
  json += "\"firmware\":\"" + String(FIRMWARE_VERSION) + "\"";
  json += "}";

  int code = http.POST(json);
  
  if (code == 200) {
    String payload = http.getString();
    // v1.2: Garage-Steuerung implementiert
    // Befehle vom Server prüfen und entsprechende Relais triggern
    if (payload.indexOf("\"trigger_tor1\":true") != -1) {
      Serial.println("[GARAGE] Befehl für Tor 1 empfangen - triggere Relais");
      triggerRelais(RELAY1_PIN);
    }
    if (payload.indexOf("\"trigger_tor2\":true") != -1) {
      Serial.println("[GARAGE] Befehl für Tor 2 empfangen - triggere Relais");
      triggerRelais(RELAY2_PIN);
    }
  }
  http.end();
}

void setup() {
  Serial.begin(115200);
  pinMode(RELAY1_PIN, OUTPUT); digitalWrite(RELAY1_PIN, HIGH);
  pinMode(RELAY2_PIN, OUTPUT); digitalWrite(RELAY2_PIN, HIGH);
  
  pinMode(sTor1.trig, OUTPUT); pinMode(sTor1.echo, INPUT);
  pinMode(sTor2.trig, OUTPUT); pinMode(sTor2.echo, INPUT);
  pinMode(sAuto1.trig, OUTPUT); pinMode(sAuto1.echo, INPUT);
  pinMode(sAuto2.trig, OUTPUT); pinMode(sAuto2.echo, INPUT);

  WiFi.begin(ssid, password);
  while (WiFi.status() != WL_CONNECTED) delay(500);

  server.on("/", handleRoot);
  server.on("/trigger/1", handleTrigger1);
  server.on("/trigger/2", handleTrigger2);
  server.on("/ota-update", handleOtaUpdate);
  server.begin();
}

void loop() {
  server.handleClient();
  static unsigned long lastUS = 0;
  if (millis() - lastUS > 1000) {
    lastUS = millis();
    sTor1.dist = messeDistanz(sTor1.trig, sTor1.echo); delay(30);
    sTor2.dist = messeDistanz(sTor2.trig, sTor2.echo); delay(30);
    sAuto1.dist = messeDistanz(sAuto1.trig, sAuto1.echo); delay(30);
    sAuto2.dist = messeDistanz(sAuto2.trig, sAuto2.echo);
  }
  if (millis() - letzterSend > SEND_INTERVAL) {
    letzterSend = millis();
    sendeAnServer();
  }
}