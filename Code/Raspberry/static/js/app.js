// ============================================================
//  ESP32 Monitor - Frontend Logik
//  Holt Daten per fetch() von /api/status und aktualisiert die
//  Seite ohne kompletten Reload (kein <meta http-equiv="refresh"> mehr).
// ============================================================

const REFRESH_MS = 3000; // alle 3 Sekunden neu abfragen

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

function renderSummary(summary) {
    document.getElementById("summary-gesamt").textContent = summary.gesamt;
    document.getElementById("summary-online").textContent = summary.online;
    document.getElementById("summary-offline").textContent = summary.offline;
    document.getElementById("footer-count").textContent = summary.gesamt;
}

function renderWaterTable(devices) {
    const tbody = document.getElementById("water-tbody");
    if (!devices || devices.length === 0) {
        tbody.innerHTML = '<tr><td colspan="10" class="no-data">Noch keine Daten von Wasser-Monitor Geraeten empfangen...</td></tr>';
        return;
    }
    let html = "";
    devices.forEach(function (d) {
        const rowClass = d.online ? "" : "device-offline";
        html += '<tr class="' + rowClass + '">';
        html += "<td>" + statusBadge(d.online) + "</td>";
        html += '<td><a href="http://' + escapeHtml(d.ip) + '" target="_blank" style="color:#00ff99;">' + escapeHtml(d.ip) + '</a> <span class="badge badge-wasser">LJ18A3</span></td>';
        html += '<td class="value-green">' + escapeHtml(d.uptime) + "</td>";
        html += '<td class="value-green">' + d.liter_gesamt.toFixed(1) + " L</td>";
        html += "<td>" + d.liter_session.toFixed(1) + " L</td>";
        html += "<td>" + d.impulse_gesamt + "</td>";
        html += '<td class="' + batterieClass(d.batterie_v) + '">' + d.batterie_v.toFixed(2) + " V</td>";
        html += '<td class="value-purple">v' + escapeHtml(d.firmware) + "</td>";
        html += "<td>" + displayBadge(d.display_an) + "</td>";
        html += '<td class="timestamp">' + escapeHtml(d.last_seen) + "</td>";
        html += "</tr>";
    });
    tbody.innerHTML = html;
}

function renderSchallTable(devices) {
    const tbody = document.getElementById("schall-tbody");
    if (!devices || devices.length === 0) {
        tbody.innerHTML = '<tr><td colspan="8" class="no-data">Noch keine Daten von Ultraschall Geraeten empfangen...</td></tr>';
        return;
    }
    let html = "";
    devices.forEach(function (d) {
        const rowClass = d.online ? "" : "device-offline";
        const distanz = d.distanz_cm === -1
            ? '<span style="color:#888;">kein Objekt</span>'
            : d.distanz_cm.toFixed(1) + " cm";
        html += '<tr class="' + rowClass + '">';
        html += "<td>" + statusBadge(d.online) + "</td>";
        html += '<td><a href="http://' + escapeHtml(d.ip) + '" target="_blank" style="color:#00d4ff;">' + escapeHtml(d.ip) + '</a> <span class="badge badge-schall">HC-SR04</span></td>';
        html += '<td class="value-blue">' + escapeHtml(d.uptime) + "</td>";
        html += '<td class="value-blue">' + distanz + "</td>";
        html += '<td class="' + batterieClass(d.batterie_v) + '">' + d.batterie_v.toFixed(2) + " V</td>";
        html += '<td class="value-purple">v' + escapeHtml(d.firmware) + "</td>";
        html += "<td>" + displayBadge(d.display_an) + "</td>";
        html += '<td class="timestamp">' + escapeHtml(d.last_seen) + "</td>";
        html += "</tr>";
    });
    tbody.innerHTML = html;
}

function renderFirmware(fw) {
    const box = document.getElementById("firmware-box");
    const lj = fw.lj18a3;
    const sc = fw.schall;
    const ljStatus = lj.ok
        ? '<span class="fw-ok">&#10003; firmware.bin vorhanden</span>'
        : '<span class="fw-miss">&#10005; firmware.bin FEHLT</span>';
    const scStatus = sc.ok
        ? '<span class="fw-ok">&#10003; firmware.bin vorhanden</span>'
        : '<span class="fw-miss">&#10005; firmware.bin FEHLT</span>';

    box.innerHTML =
        "<p>" +
        '<strong style="color:#00ff99;">LJ18A3 Firmware:</strong> ' +
        "Version <code>" + escapeHtml(lj.version) + "</code> &nbsp;|&nbsp; " +
        ljStatus +
        " &nbsp;|&nbsp; Endpunkte: " +
        "<code>/firmware/lj18a3/version</code> " +
        "<code>/firmware/lj18a3/download</code>" +
        "</p>" +
        "<p>" +
        '<strong style="color:#00d4ff;">Schall Firmware:</strong> ' +
        "Version <code>" + escapeHtml(sc.version) + "</code> &nbsp;|&nbsp; " +
        scStatus +
        " &nbsp;|&nbsp; Endpunkte: " +
        "<code>/firmware/schall/version</code> " +
        "<code>/firmware/schall/download</code>" +
        "</p>" +
        '<p style="color:#555; font-size:0.85em; margin-top:10px;">' +
        "Firmware .bin ablegen in: <code>firmware/lj18a3/firmware.bin</code> bzw. " +
        "<code>firmware/schall/firmware.bin</code> &nbsp;|&nbsp; " +
        "Version in: <code>firmware/lj18a3/version.txt</code> bzw. " +
        "<code>firmware/schall/version.txt</code>" +
        "</p>";
}

function renderMessages(messages) {
    const tbody = document.getElementById("messages-tbody");
    if (!messages || messages.length === 0) {
        tbody.innerHTML = '<tr><td colspan="9" class="no-data">Noch keine Daten empfangen...</td></tr>';
        return;
    }
    let html = "";
    messages.forEach(function (m) {
        html += "<tr>";
        html += '<td class="timestamp">' + escapeHtml(m.zeit) + "</td>";
        html += "<td>" + escapeHtml(m.ip) + "</td>";
        html += "<td>" + (m.typ === "LJ18A3"
            ? '<span class="badge badge-wasser">LJ18A3</span>'
            : '<span class="badge badge-schall">HC-SR04</span>') + "</td>";
        html += '<td style="font-size: 0.85em; color: #aaa;">' + escapeHtml(m.details) + "</td>";

        if (m.typ === "LJ18A3") {
            html += '<td style="color:#00ff99;">' + m.impulse_gesamt + "</td>";
            html += '<td style="color:#00ff99; font-weight:bold;">' + m.liter_gesamt.toFixed(1) + " L</td>";
            html += '<td style="color:#aaa;">' + m.liter_session.toFixed(1) + " L</td>";
            html += '<td style="color:#555;">&#8212;</td>';
            html += '<td class="' + batterieClass(m.batterie_v) + '">' + m.batterie_v.toFixed(2) + " V</td>";
        } else {
            html += '<td style="color:#555;">&#8212;</td>';
            html += '<td style="color:#555;">&#8212;</td>';
            html += '<td style="color:#555;">&#8212;</td>';
            const distanz = m.distanz_cm === -1
                ? '<span style="color:#888;">kein Objekt</span>'
                : m.distanz_cm.toFixed(1) + " cm";
            html += '<td style="color:#00d4ff;">' + distanz + "</td>";
            html += '<td class="' + batterieClass(m.batterie_v) + '">' + m.batterie_v.toFixed(2) + " V</td>";
        }
        html += "</tr>";
    });
    tbody.innerHTML = html;
}

function setLiveIndicator(ok) {
    const dot = document.getElementById("refresh-indicator");
    if (!dot) return;
    dot.classList.toggle("live-dot-error", !ok);
}

function fetchStatus() {
    fetch("/api/status")
        .then(function (response) {
            if (!response.ok) {
                throw new Error("HTTP " + response.status);
            }
            return response.json();
        })
        .then(function (data) {
            document.getElementById("last-updated").textContent = data.now;
            document.getElementById("offline-secs").textContent = data.offline_secs;
            const versionTag = document.getElementById("version-tag");
            if (versionTag && data.server_version) {
                versionTag.textContent = "v" + data.server_version;
            }
            renderSummary(data.summary);
            renderWaterTable(data.devices_lj18a3);
            renderSchallTable(data.devices_schall);
            renderFirmware(data.firmware);
            renderMessages(data.messages);
            setLiveIndicator(true);
        })
        .catch(function (err) {
            console.error("Fehler beim Abrufen von /api/status:", err);
            setLiveIndicator(false);
        });
}

// Sofort beim Laden der Seite abrufen, danach alle REFRESH_MS Millisekunden
document.addEventListener("DOMContentLoaded", function () {
    fetchStatus();
    setInterval(fetchStatus, REFRESH_MS);
});
