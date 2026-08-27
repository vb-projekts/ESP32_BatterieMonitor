const REFRESH_MS = 3000;
function renderSummary(summary) {
    document.getElementById("summary-gesamt").textContent = summary.gesamt;
    document.getElementById("summary-online").textContent = summary.online;
    document.getElementById("summary-offline").textContent = summary.offline;
    document.getElementById("footer-count").textContent = summary.gesamt;
}
function renderWaterTable(devices) {
    const tbody = document.getElementById("water-tbody");
    if (!devices || devices.length === 0) { tbody.innerHTML = '<tr><td colspan="10" class="no-data">Keine Daten...</td></tr>'; return; }
    let html = "";
    devices.forEach(d => {
        html += `<tr class="${d.online ? '' : 'device-offline'}">
            <td>${statusBadge(d.online)}</td>
            <td><a href="http://${d.ip}" target="_blank" style="color:#00ff99;">${d.ip}</a> <span class="badge badge-wasser">LJ18A3</span></td>
            <td class="value-green">${d.uptime}</td><td class="value-green">${d.liter_lebenszeit.toFixed(1)} L</td>
            <td>${d.liter_gesamt.toFixed(1)} L</td><td>${d.impulse_gesamt}</td>
            <td class="${batterieClass(d.batterie_v)}">${d.batterie_v.toFixed(2)} V</td>
            <td class="value-purple">v${d.firmware}</td><td>${displayBadge(d.display_an)}</td>
            <td class="timestamp">${d.last_seen}</td></tr>`;
    });
    tbody.innerHTML = html;
}
function renderGarageTable(devices) {
    const tbody = document.getElementById("garage-tbody");
    if (!devices || devices.length === 0) { tbody.innerHTML = '<tr><td colspan="9" class="no-data">Keine Daten...</td></tr>'; return; }
    let html = "";
    devices.forEach(d => {
        html += `<tr class="${d.online ? '' : 'device-offline'}">
            <td>${statusBadge(d.online)}</td>
            <td><a href="http://${d.ip}" target="_blank" style="color:#e8b86d;">${d.ip}</a> <span class="badge badge-garage">Garage</span></td>
            <td class="value-blue">${d.uptime}</td><td>${d.tor1_cm.toFixed(0)} cm</td><td>${d.tor2_cm.toFixed(0)} cm</td>
            <td>${d.auto1_cm.toFixed(0)} cm</td><td>${d.auto2_cm.toFixed(0)} cm</td>
            <td class="value-purple">v${d.firmware}</td><td class="timestamp">${d.last_seen}</td></tr>`;
    });
    tbody.innerHTML = html;
}
function renderSchallTable(devices) {
    const tbody = document.getElementById("schall-tbody");
    if (!devices || devices.length === 0) { tbody.innerHTML = '<tr><td colspan="8" class="no-data">Keine Daten...</td></tr>'; return; }
    let html = "";
    devices.forEach(d => {
        html += `<tr class="${d.online ? '' : 'device-offline'}">
            <td>${statusBadge(d.online)}</td>
            <td><a href="http://${d.ip}" target="_blank" style="color:#00d4ff;">${d.ip}</a> <span class="badge badge-schall">HC-SR04</span></td>
            <td class="value-blue">${d.uptime}</td><td>${d.distanz_cm.toFixed(1)} cm</td>
            <td class="${batterieClass(d.batterie_v)}">${d.batterie_v.toFixed(2)} V</td>
            <td class="value-purple">v${d.firmware}</td><td>${displayBadge(d.display_an)}</td>
            <td class="timestamp">${d.last_seen}</td></tr>`;
    });
    tbody.innerHTML = html;
}
function renderFirmware(fw) {
    const box = document.getElementById("firmware-box");
    box.innerHTML = `
        <p><strong style="color:#00ff99;">LJ18A3:</strong> v${fw.lj18a3.version} | ${fw.lj18a3.ok ? 'OK' : 'FEHLT'}</p>
        <p><strong style="color:#00d4ff;">Schall:</strong> v${fw.schall.version} | ${fw.schall.ok ? 'OK' : 'FEHLT'}</p>
        <p><strong style="color:#e8b86d;">Garage:</strong> v${fw.garage.version} | ${fw.garage.ok ? 'OK' : 'FEHLT'}</p>`;
}
function renderMessages(messages) {
    const tbody = document.getElementById("messages-tbody");
    if (!messages || messages.length === 0) { tbody.innerHTML = '<tr><td colspan="8" class="no-data">Keine Daten...</td></tr>'; return; }
    let html = "";
    messages.forEach(m => {
        html += `<tr><td class="timestamp">${m.zeit}</td><td>${m.ip}</td>
            <td><span class="badge badge-${m.typ.toLowerCase()}">${m.typ}</span></td>
            <td style="font-size:0.85em; color:#aaa;">${m.details}</td>
            <td>${m.impulse_gesamt || '—'}</td><td>${m.liter_gesamt ? m.liter_gesamt.toFixed(1) : '—'}</td>
            <td>${m.distanz_cm !== -1 ? m.distanz_cm.toFixed(1) : '—'}</td>
            <td class="${batterieClass(m.batterie_v)}">${m.batterie_v.toFixed(2)} V</td></tr>`;
    });
    tbody.innerHTML = html;
}
function fetchStatus() {
    fetch("/api/status").then(res => res.json()).then(data => {
        document.getElementById("last-updated").textContent = data.now;
        document.getElementById("offline-secs").textContent = data.offline_secs;
        renderSummary(data.summary); renderWaterTable(data.devices_lj18a3);
        renderGarageTable(data.devices_garage); renderSchallTable(data.devices_schall);
        renderFirmware(data.firmware); renderMessages(data.messages);
        setLiveIndicator("refresh-indicator", true);
    }).catch(() => setLiveIndicator("refresh-indicator", false));
}
document.addEventListener("DOMContentLoaded", () => { fetchStatus(); setInterval(fetchStatus, REFRESH_MS); });
