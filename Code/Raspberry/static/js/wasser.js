// ============================================================
//  Wasserverbrauch-Seite ("/wasser") - Frontend Logik
//  Holt Daten per fetch() von /api/wasser und aktualisiert die
//  Seite alle 2 Sekunden ohne Reload. Zeigt pro Geraet ein
//  rotierendes "Wasserrad", das sich mit dem Durchfluss dreht.
//  Gemeinsame Helfer (escapeHtml, statusBadge, displayBadge,
//  batterieClass, setLiveIndicator) kommen aus common.js.
// ============================================================

const WASSER_REFRESH_MS = 1000; // schnellere Reaktionszeit (vorher 2000ms)

function berechneSpinDauer(lProMin) {
    // Kein spuerbarer Durchfluss -> Rad steht still
    if (!lProMin || lProMin < 0.05) {
        return null;
    }
    // Je hoeher der Durchfluss, desto schneller dreht sich das Rad
    const dauer = 8 / lProMin;
    return Math.max(0.4, Math.min(dauer, 10));
}

function baueMeterKarte(d, index) {
    const rowClass = d.online ? "" : "device-offline";
    const wheelId = "meter-wheel-" + index;
    const durchfluss = d.durchfluss_l_min || 0;

    let html = "";
    html += '<div class="meter-card ' + rowClass + '">';
    html += '<div class="meter-card-header">';
    html += statusBadge(d.online);
    html += '<span class="meter-ip"><a href="http://' + escapeHtml(d.ip) + '" target="_blank" style="color:#00ff99;">' + escapeHtml(d.ip) + '</a></span>';
    html += '</div>';

    html += '<div class="meter-body">';
    html += '<div class="meter-wheel-wrap">';
    html += '<svg viewBox="0 0 100 100" class="meter-wheel">';
    html += '<circle cx="50" cy="50" r="46" class="wheel-ring"></circle>';
    html += '<g transform="translate(50,50)">';
    html += '<g class="wheel-star" id="' + wheelId + '">';
    html += '<polygon points="0,-42 9,-9 42,0 9,9 0,42 -9,9 -42,0 -9,-9"></polygon>';
    html += '</g>';
    html += '</g>';
    html += '</svg>';
    html += '</div>';

    html += '<div class="meter-numbers">';
    html += '<div class="meter-num-block">';
    html += '<span class="meter-num-value value-green">' + d.liter_gesamt.toFixed(1) + ' L</span>';
    html += '<span class="meter-num-label">Gesamtverbrauch</span>';
    html += '</div>';
    html += '<div class="meter-num-block">';
    html += '<span class="meter-num-value">' + d.liter_session.toFixed(1) + ' L</span>';
    html += '<span class="meter-num-label">Diese Session</span>';
    html += '</div>';
    html += '<div class="meter-num-block">';
    html += '<span class="meter-num-value value-purple">' + durchfluss.toFixed(2) + ' L/min</span>';
    html += '<span class="meter-num-label">Aktueller Durchfluss</span>';
    html += '</div>';
    html += '</div>'; // meter-numbers
    html += '</div>'; // meter-body

    html += '<div class="meter-footer">';
    html += 'Batterie: <span class="' + batterieClass(d.batterie_v) + '">' + d.batterie_v.toFixed(2) + ' V</span>';
    html += ' &nbsp;|&nbsp; Firmware v' + escapeHtml(d.firmware);
    html += ' &nbsp;|&nbsp; Display: ' + displayBadge(d.display_an);
    html += ' &nbsp;|&nbsp; Letztes Update: ' + escapeHtml(d.last_seen);
    html += '</div>';
    html += '</div>'; // meter-card

    return html;
}

function renderMeterKarten(geraete) {
    const container = document.getElementById("meter-cards");
    if (!geraete || geraete.length === 0) {
        container.innerHTML = '<p class="no-data">Noch keine Daten von Wasser-Monitor Geraeten empfangen...</p>';
        return;
    }

    let html = "";
    geraete.forEach(function (d, index) {
        html += baueMeterKarte(d, index);
    });
    container.innerHTML = html;

    // Erst NACHDEM die Elemente im DOM sind, die Drehgeschwindigkeit setzen
    geraete.forEach(function (d, index) {
        const rad = document.getElementById("meter-wheel-" + index);
        if (!rad) return;
        const dauer = berechneSpinDauer(d.durchfluss_l_min);
        if (dauer === null) {
            rad.classList.remove("spinning");
        } else {
            rad.style.animationDuration = dauer.toFixed(2) + "s";
            rad.classList.add("spinning");
        }
    });
}

function renderWasserSummary(summary) {
    document.getElementById("wasser-summary-gesamt").textContent = summary.liter_gesamt.toFixed(1) + " L";
    document.getElementById("wasser-summary-session").textContent = summary.liter_session.toFixed(1) + " L";
    document.getElementById("wasser-summary-durchfluss").textContent = summary.durchfluss_l_min.toFixed(2);
}

function fetchWasserStatus() {
    fetch("/api/wasser")
        .then(function (response) {
            if (!response.ok) {
                throw new Error("HTTP " + response.status);
            }
            return response.json();
        })
        .then(function (data) {
            document.getElementById("wasser-last-updated").textContent = data.now;
            const versionTag = document.getElementById("version-tag");
            if (versionTag && data.server_version) {
                versionTag.textContent = "v" + data.server_version;
            }
            renderWasserSummary(data.summary);
            renderMeterKarten(data.geraete);
            setLiveIndicator("wasser-refresh-indicator", true);
        })
        .catch(function (err) {
            console.error("Fehler beim Abrufen von /api/wasser:", err);
            setLiveIndicator("wasser-refresh-indicator", false);
        });
}

document.addEventListener("DOMContentLoaded", function () {
    fetchWasserStatus();
    setInterval(fetchWasserStatus, WASSER_REFRESH_MS);
});
