// ============================================================
//  Wasserverbrauch-Seite ("/wasser") - Frontend Logik
//  Holt Daten per fetch() von /api/wasser (Meter-Karten, alle 1s) und
//  /api/wasser/verlauf (Diagramm, alle 5s) und aktualisiert die Seite
//  ohne Reload. Zeigt pro Geraet ein rotierendes "Wasserrad" und
//  erlaubt per Klick auf eine Karte die Auswahl des Geraets fuers
//  Diagramm unten (markiert mit Rahmen + Augen-Symbol).
//  Gemeinsame Helfer (escapeHtml, statusBadge, displayBadge,
//  batterieClass, setLiveIndicator) kommen aus common.js.
// ============================================================

const WASSER_REFRESH_MS = 1000;  // Meter-Karten: sehr zeitnah
const CHART_REFRESH_MS = 5000;   // Diagramm: reicht seltener zu aktualisieren

let ausgewaehlteIp = null;      // IP des per Klick ausgewaehlten Geraets
let aktuellerZeitraum = "stunde";
let verbrauchChart = null;      // Chart.js-Instanz (wird einmal erstellt, dann aktualisiert)

function berechneSpinDauer(lProMin) {
    if (!lProMin || lProMin < 0.05) {
        return null;
    }
    const dauer = 8 / lProMin;
    return Math.max(0.4, Math.min(dauer, 10));
}

function baueMeterKarte(d, index) {
    const rowClass = d.online ? "" : "device-offline";
    const wheelId = "meter-wheel-" + index;
    const durchfluss = d.durchfluss_l_min || 0;
    const istAusgewaehlt = d.ip === ausgewaehlteIp;

    let html = "";
    html += '<div class="meter-card ' + rowClass + (istAusgewaehlt ? " selected" : "") + '" data-ip="' + escapeHtml(d.ip) + '">';
    html += '<span class="eye-badge">&#128065; Ausgewählt</span>';
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
    html += '<span class="meter-num-value value-green">' + d.liter_lebenszeit.toFixed(1) + ' L</span>';
    html += '<span class="meter-num-label">Gesamtverbrauch</span>';
    html += '</div>';
    html += '<div class="meter-num-block">';
    html += '<span class="meter-num-value">' + d.liter_gesamt.toFixed(1) + ' L</span>';
    html += '<span class="meter-num-label">Seit Neustart</span>';
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
    html += '<div class="meter-hint">Zum Auswählen fürs Diagramm anklicken</div>';
    html += '</div>'; // meter-card

    return html;
}

function renderMeterKarten(geraete) {
    const container = document.getElementById("meter-cards");
    if (!geraete || geraete.length === 0) {
        container.innerHTML = '<p class="no-data">Noch keine Daten von Wasser-Monitor Geräten empfangen...</p>';
        return;
    }

    let html = "";
    geraete.forEach(function (d, index) {
        html += baueMeterKarte(d, index);
    });
    container.innerHTML = html;

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
    document.getElementById("wasser-summary-gesamt").textContent = summary.liter_lebenszeit.toFixed(1) + " L";
    document.getElementById("wasser-summary-neustart").textContent = summary.liter_seit_neustart.toFixed(1) + " L";
    document.getElementById("wasser-summary-durchfluss").textContent = summary.durchfluss_l_min.toFixed(2);
}

// ------------------------------------------------------------------
// Diagramm (Chart.js)
// ------------------------------------------------------------------

function formatiereChartLabel(zeitraum, label) {
    if (zeitraum === "stunde") {
        // "2026-08-25 12" -> "25.08. 12:00"
        const teile = label.split(" ");
        const datum = teile[0].split("-");
        return datum[2] + "." + datum[1] + ". " + teile[1] + ":00";
    }
    if (zeitraum === "tag") {
        // "2026-08-25" -> "25.08."
        const datum = label.split("-");
        return datum[2] + "." + datum[1] + ".";
    }
    return label; // "woche" (2026-KW34) und "monat" (2026-08) sind schon gut lesbar
}

function erstelleOderAktualisiereChart(labels, werte, zeitraum, geraeteIp) {
    const canvas = document.getElementById("verbrauch-chart");
    if (!canvas || typeof Chart === "undefined") {
        return; // chart.min.js noch nicht eingebunden/gefunden
    }
    const angezeigteLabels = labels.map(function (l) {
        return formatiereChartLabel(zeitraum, l);
    });

    if (verbrauchChart) {
        verbrauchChart.data.labels = angezeigteLabels;
        verbrauchChart.data.datasets[0].data = werte;
        verbrauchChart.update();
        return;
    }

    verbrauchChart = new Chart(canvas, {
        type: "bar",
        data: {
            labels: angezeigteLabels,
            datasets: [{
                label: "Verbrauch in Liter",
                data: werte,
                backgroundColor: "#00d4ffaa",
                borderColor: "#00d4ff",
                borderWidth: 1,
                borderRadius: 4,
                maxBarThickness: 40,
            }],
        },
        options: {
            responsive: true,
            plugins: {
                legend: { display: false },
            },
            scales: {
                x: {
                    ticks: { color: "#888" },
                    grid: { color: "#0f3460" },
                },
                y: {
                    beginAtZero: true,
                    ticks: { color: "#888" },
                    grid: { color: "#0f3460" },
                    title: { display: true, text: "Liter", color: "#888" },
                },
            },
        },
    });
}

function fetchVerlaufChart() {
    if (!ausgewaehlteIp) {
        return;
    }
    const url = "/api/wasser/verlauf?ip=" + encodeURIComponent(ausgewaehlteIp) +
                "&zeitraum=" + encodeURIComponent(aktuellerZeitraum);
    fetch(url)
        .then(function (response) {
            if (!response.ok) {
                throw new Error("HTTP " + response.status);
            }
            return response.json();
        })
        .then(function (data) {
            erstelleOderAktualisiereChart(data.labels, data.werte, data.zeitraum, data.ip);
            const label = document.getElementById("chart-geraet-label");
            if (label) {
                label.textContent = "Gerät: " + data.ip;
            }
        })
        .catch(function (err) {
            console.error("Fehler beim Abrufen von /api/wasser/verlauf:", err);
        });
}

function waehleGeraetAus(ip) {
    if (!ip || ip === ausgewaehlteIp) {
        return;
    }
    ausgewaehlteIp = ip;
    // Sofortiges visuelles Feedback, ohne auf den naechsten Poll zu warten
    document.querySelectorAll("#meter-cards .meter-card").forEach(function (el) {
        el.classList.toggle("selected", el.getAttribute("data-ip") === ip);
    });
    fetchVerlaufChart();
}

// ------------------------------------------------------------------
// Meter-Karten / Summary abrufen
// ------------------------------------------------------------------

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

            // Beim allerersten erfolgreichen Laden automatisch das erste
            // Geraet auswaehlen, damit sofort ein Diagramm zu sehen ist.
            const istErsterLoad = (ausgewaehlteIp === null);
            if (istErsterLoad && data.geraete && data.geraete.length > 0) {
                ausgewaehlteIp = data.geraete[0].ip;
            }

            renderMeterKarten(data.geraete);

            if (istErsterLoad) {
                fetchVerlaufChart();
            }

            setLiveIndicator("wasser-refresh-indicator", true);
        })
        .catch(function (err) {
            console.error("Fehler beim Abrufen von /api/wasser:", err);
            setLiveIndicator("wasser-refresh-indicator", false);
        });
}

document.addEventListener("DOMContentLoaded", function () {
    // Klick auf eine meter-card -> Geraet fuers Diagramm auswaehlen
    // (Event-Delegation, da die Karten dynamisch neu erzeugt werden)
    const kartenContainer = document.getElementById("meter-cards");
    if (kartenContainer) {
        kartenContainer.addEventListener("click", function (e) {
            const karte = e.target.closest(".meter-card");
            if (!karte) return;
            waehleGeraetAus(karte.getAttribute("data-ip"));
        });
    }

    // Zeitraum-Buttons (Stunde/Tag/Woche/Monat)
    document.querySelectorAll(".zeitraum-btn").forEach(function (btn) {
        btn.addEventListener("click", function () {
            document.querySelectorAll(".zeitraum-btn").forEach(function (b) {
                b.classList.remove("active");
            });
            btn.classList.add("active");
            aktuellerZeitraum = btn.getAttribute("data-zeitraum");
            fetchVerlaufChart();
        });
    });

    fetchWasserStatus();
    setInterval(fetchWasserStatus, WASSER_REFRESH_MS);
    setInterval(fetchVerlaufChart, CHART_REFRESH_MS);
});
