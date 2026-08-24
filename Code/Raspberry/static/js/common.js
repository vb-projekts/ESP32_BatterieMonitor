// ============================================================
//  ESP32 Monitor - Gemeinsame Frontend-Helfer
//  Wird auf JEDER Seite geladen (siehe base.html), damit Uebersicht,
//  Wasserverbrauch und kuenftige Seiten dieselben Bausteine nutzen
//  koennen, statt sie mehrfach zu implementieren.
// ============================================================

function escapeHtml(text) {
    const div = document.createElement("div");
    div.textContent = String(text);
    return div.innerHTML;
}

function statusBadge(online) {
    if (online) {
        return '<span class="status-badge online"><span class="status-dot"></span>ONLINE</span>';
    }
    return '<span class="status-badge offline"><span class="status-dot"></span>OFFLINE</span>';
}

function displayBadge(displayAn) {
    if (displayAn) {
        return '<span style="color:#00ff99; font-weight:bold;">&#128994; AN</span>';
    }
    return '<span style="color:#888;">&#9898; AUS</span>';
}

function batterieClass(v) {
    return v < 12.0 ? "value-warn" : "value-ok";
}

function setLiveIndicator(elementId, ok) {
    const dot = document.getElementById(elementId);
    if (!dot) return;
    dot.classList.toggle("live-dot-error", !ok);
}
