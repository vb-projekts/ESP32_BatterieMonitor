const REFRESH_MS = 2000;

function triggerGate(ip, torNum) {
    fetch('/api/garage/control', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ip: ip, tor: torNum })
    }).then(res => res.json()).then(data => {
        alert("Befehl für Tor " + torNum + " gesendet!");
    });
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
        
        // Prozentberechnung für Tore (0% = Zu, 100% = Auf)
        // Wir nehmen an: max_cm = Zu, min_cm = Auf
        const t1_perc = Math.max(0, Math.min(100, ((config.tor1.max - dev.tor1_cm) / (config.tor1.max - config.tor1.min)) * 100));
        const t2_perc = Math.max(0, Math.min(100, ((config.tor2.max - dev.tor2_cm) / (config.tor2.max - config.tor2.min)) * 100));
        
        // Auto Präsenz
        const a1_present = dev.auto1_cm < config.auto1.threshold;
        const a2_present = dev.auto2_cm < config.auto2.threshold;

        html += `
            <div class="garage-bay ${dev.online ? '' : 'device-offline'}">
                <h3>Doppelgarage (${dev.ip})</h3>
                <div style="display:flex; gap:10px; justify-content: center;">
                    <div style="flex:1; max-width: 250px;">
                        <div class="status-text" style="color:#e8b86d">Tor 1</div>
                        <div class="visual-box">
                            <div class="gate-door" style="height: ${100 - t1_perc}%"></div>
                            <div class="car-spot" style="opacity: ${a1_present ? 1 : 0.1}">🚗</div>
                        </div>
                        <div class="dist-text">${dev.tor1_cm.toFixed(0)}cm / ${a1_present ? 'Belegt' : 'Frei'}</div>
                        <button class="btn-trigger" onclick="triggerGate('${dev.ip}', 1)">Taster 1</button>
                    </div>
                    <div style="flex:1; max-width: 250px;">
                        <div class="status-text" style="color:#e8b86d">Tor 2</div>
                        <div class="visual-box">
                            <div class="gate-door" style="height: ${100 - t2_perc}%"></div>
                            <div class="car-spot" style="opacity: ${a2_present ? 1 : 0.1}">🚗</div>
                        </div>
                        <div class="dist-text">${dev.tor2_cm.toFixed(0)}cm / ${a2_present ? 'Belegt' : 'Frei'}</div>
                        <button class="btn-trigger" onclick="triggerGate('${dev.ip}', 2)">Taster 2</button>
                    </div>
                </div>
                <div class="footer" style="margin-top:15px">Uptime: ${dev.uptime} | v${dev.firmware}</div>
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
