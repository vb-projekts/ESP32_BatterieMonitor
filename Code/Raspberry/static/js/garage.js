const REFRESH_MS = 2000;
let historyVisible = false;

function triggerGate(ip, torNum) {
    fetch('/api/garage/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip: ip, tor: torNum })
    }).then(res => res.json()).then(data => {
        alert("Befehl für Tor " + torNum + " gesendet!");
    });
}

function toggleHistory() {
    historyVisible = !historyVisible;
    const historyDiv = document.getElementById('garage-history');
    const eyeIcon = document.getElementById('eye-icon');
    
    if (historyVisible) {
        historyDiv.style.display = 'block';
        eyeIcon.textContent = '👁️';
        fetchGarageHistory();
    } else {
        historyDiv.style.display = 'none';
        eyeIcon.textContent = '👁️‍🗨️';
    }
}

function formatDuration(seconds) {
    if (seconds === null) return '--:--:--';
    const h = Math.floor(seconds / 3600);
    const m = Math.floor((seconds % 3600) / 60);
    const s = seconds % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
}

function formatDateTime(isoString) {
    if (!isoString) return '--';
    const date = new Date(isoString);
    return date.toLocaleString('de-DE', { 
        day: '2-digit', 
        month: '2-digit', 
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
}

function fetchGarageHistory() {
    fetch('/api/garage/history')
        .then(res => res.json())
        .then(data => {
            updateHistoryUI(data);
        })
        .catch(err => console.error("Fehler beim Abrufen der History:", err));
}

function updateHistoryUI(data) {
    const historyDiv = document.getElementById('garage-history');
    let html = '<h3>📊 Fahrtenverlauf</h3>';
    
    for (const [ip, trips] of Object.entries(data)) {
        html += `<div style="margin-bottom: 30px;">`;
        html += `<h4>${ip}</h4>`;
        
        // Tor 1
        html += `<div style="margin-bottom: 20px;">`;
        html += `<h5>🔵 Tor 1 - Ford Focus</h5>`;
        html += buildTripsTable(trips.tor1_trips, 'ford');
        html += `</div>`;
        
        // Tor 2
        html += `<div style="margin-bottom: 20px;">`;
        html += `<h5>⚫ Tor 2 - BMW</h5>`;
        html += buildTripsTable(trips.tor2_trips, 'bmw');
        html += `</div>`;
        
        html += `</div>`;
    }
    
    historyDiv.innerHTML = html;
}

function buildTripsTable(trips, autoType) {
    if (!trips || trips.length === 0) {
        return '<p style="color: #999;">Keine Fahrten erfasst.</p>';
    }
    
    const carEmoji = autoType === 'ford' ? '🔵' : '⚫';
    
    let html = `<table style="width: 100%; border-collapse: collapse; background: #0a1128; border-radius: 8px; overflow: hidden;">`;
    html += `<tr style="background: #16213e; border-bottom: 1px solid #0f3460;">`;
    html += `<th style="padding: 10px; text-align: left; color: #e8b86d;">Auto</th>`;
    html += `<th style="padding: 10px; text-align: left; color: #e8b86d;">Verlassen</th>`;
    html += `<th style="padding: 10px; text-align: left; color: #e8b86d;">Angekommen</th>`;
    html += `<th style="padding: 10px; text-align: left; color: #e8b86d;">Dauer</th>`;
    html += `</tr>`;
    
    trips.forEach(trip => {
        html += `<tr style="border-bottom: 1px solid #0f3460;">`;
        html += `<td style="padding: 10px;">${carEmoji}</td>`;
        html += `<td style="padding: 10px;">${formatDateTime(trip.verlassen_zeit)}</td>`;
        html += `<td style="padding: 10px;">${formatDateTime(trip.angekommen_zeit)}</td>`;
        html += `<td style="padding: 10px; color: #51cf66; font-weight: bold;">${formatDuration(trip.dauer_sekunden)}</td>`;
        html += `</tr>`;
    });
    
    html += `</table>`;
    return html;
}

function updateUI(data) {
    const container = document.getElementById('garage-container');
    document.getElementById('last-updated').textContent = data.now;
    
    if (!data.devices || data.devices.length === 0) {
        container.innerHTML = '<p class="no-data">Kein Garage-Board online.</p>';
        return;
    }

    let html = "";
    data.devices.forEach(dev => {
        const config = data.config;
        
        const t1_perc = Math.max(0, Math.min(100, ((config.tor1.max - dev.tor1_cm) / (config.tor1.max - config.tor1.min)) * 100));
        const t2_perc = Math.max(0, Math.min(100, ((config.tor2.max - dev.tor2_cm) / (config.tor2.max - config.tor2.min)) * 100));
        
        const a1_present = dev.auto1_cm < config.auto1.threshold;
        const a2_present = dev.auto2_cm < config.auto2.threshold;
        
        const a1_opacity = a1_present ? 1 : 0.2;
        const a2_opacity = a2_present ? 1 : 0.2;
        
        const a1_status = a1_present ? '<span style="color: #ff6b6b; font-weight: bold; font-size: 1.1em;">BELEGT</span>' : '<span style="color: #51cf66; font-weight: bold; font-size: 1.1em;">FREI</span>';
        const a2_status = a2_present ? '<span style="color: #ff6b6b; font-weight: bold; font-size: 1.1em;">BELEGT</span>' : '<span style="color: #51cf66; font-weight: bold; font-size: 1.1em;">FREI</span>';

        html += `
            <div class="garage-bay ${dev.online ? '' : 'device-offline'}">
                <h3>🏠 Doppelgarage</h3>
                <div style="display:flex; gap:20px; justify-content: center; margin-top: 20px;">
                    <div style="flex:1; max-width: 250px;">
                        <div class="status-text" style="color:#e8b86d; margin-bottom: 10px;">Tor 1 - Ford Focus</div>
                        <button class="btn-trigger" onclick="triggerGate('${dev.ip}', 1)" style="margin-bottom: 15px;">Taster 1</button>
                        <div class="visual-box">
                            <div class="gate-door" style="height: ${100 - t1_perc}%"></div>
                            <img src="/static/img/Ford_Focus_Seite.jpg" alt="Ford Focus" style="position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%); max-height: 120px; max-width: 180px; object-fit: contain; opacity: ${a1_opacity}; transition: opacity 0.3s; z-index: 1; pointer-events: none;">
                        </div>
                        <div class="dist-text" style="margin-top: 12px;">${a1_status}</div>
                    </div>
                    <div style="flex:1; max-width: 250px;">
                        <div class="status-text" style="color:#e8b86d; margin-bottom: 10px;">Tor 2 - BMW</div>
                        <button class="btn-trigger" onclick="triggerGate('${dev.ip}', 2)" style="margin-bottom: 15px;">Taster 2</button>
                        <div class="visual-box">
                            <div class="gate-door" style="height: ${100 - t2_perc}%"></div>
                            <img src="/static/img/BMW_F30_Seite.jpg" alt="BMW" style="position: absolute; bottom: 10px; left: 50%; transform: translateX(-50%); max-height: 120px; max-width: 180px; object-fit: contain; opacity: ${a2_opacity}; transition: opacity 0.3s; z-index: 1; pointer-events: none;">
                        </div>
                        <div class="dist-text" style="margin-top: 12px;">${a2_status}</div>
                    </div>
                </div>
                <div class="footer" style="margin-top:20px; font-size: 0.9em; color: #999;">Uptime: ${dev.uptime} | v${dev.firmware}</div>
            </div>
        `;
    });
    container.innerHTML = html;
}

function fetchGarage() {
    fetch('/api/garage')
        .then(res => res.json())
        .then(data => {
            updateUI(data);
            setLiveIndicator("refresh-indicator", true);
        })
        .catch(err => {
            console.error("Fehler beim Abrufen der Garage-Daten:", err);
            setLiveIndicator("refresh-indicator", false);
        });
}

document.addEventListener("DOMContentLoaded", () => {
    fetchGarage();
    setInterval(fetchGarage, REFRESH_MS);
});
